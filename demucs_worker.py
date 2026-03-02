import os
import sys
import time
import socket
import json
import threading
import torch
from demucs.separate import main as demucs_main
from demucs.pretrained import get_model
from demucs.apply import apply_model
from demucs.audio import AudioFile, save_audio

# Configuration
SOCKET_PATH = "/tmp/demucs_worker.sock"
INACTIVITY_TIMEOUT = 30 * 60  # 30 minutes
MODEL_NAME = "htdemucs"

class DemucsWorker:
    def __init__(self):
        self.model = None
        self.last_active = time.time()
        self.running = True
        self.lock = threading.Lock()

    def load_model(self):
        if self.model is None:
            print(f"[worker] Loading model {MODEL_NAME}...")
            self.model = get_model(MODEL_NAME)
            if torch.cuda.is_available():
                self.model.cuda()
            print("[worker] Model loaded.")

    def separate(self, input_path, output_dir, taskId, conn=None):
        def send_status(step, progress=0):
            if conn:
                try:
                    conn.sendall(json.dumps({"type": "progress", "step": step, "progress": progress}).encode() + b"\n")
                except:
                    pass

        send_status("Loading Demucs model...", 5)
        self.load_model()
        self.last_active = time.time()
        
        try:
            from demucs.audio import AudioFile
            from demucs.apply import apply_model
            import torch

            send_status("Reading audio file...", 15)
            wav = AudioFile(input_path).read(streams=0, samplerate=self.model.samplerate, channels=self.model.audio_channels)
            wav = wav.to(next(self.model.parameters()).device)
            
            send_status("Normalizing audio...", 25)
            ref = wav.mean(0)
            wav -= ref.mean()
            wav /= ref.std()

            send_status("Processing audio in segments...", 40)
            
            # htdemucs can be quite heavy. We can use segment and tqdm-like logic 
            # by splitting the audio manually or letting apply_model do segments but we won't get callbacks.
            # Instead of complex chunking, let's at least provide more "fake" steps if we can't get real ones,
            # OR use the 'progress' flag and try to capture stderr (hard in this architecture).
            
            # Actually, apply_model has a 'segment' parameter.
            # Let's try to process in 30s segments manually to give real feedback.
            
            duration = wav.shape[1] / self.model.samplerate
            segment_length = 30 # seconds
            total_segments = int(duration / segment_length) + 1
            
            all_sources = []
            for i in range(total_segments):
                start = i * segment_length * self.model.samplerate
                end = min((i + 1) * segment_length * self.model.samplerate, wav.shape[1])
                if start >= wav.shape[1]: break
                
                chunk = wav[:, start:end]
                send_status(f"Separating segment {i+1}/{total_segments}...", 40 + int((i / total_segments) * 40))
                
                # Process chunk
                chunk_sources = apply_model(self.model, chunk[None], num_workers=1)[0]
                all_sources.append(chunk_sources)
            
            sources = torch.cat(all_sources, dim=1)

            send_status("Saving stems...", 85)
            stem_names = self.model.sources
            vocals_idx = stem_names.index('vocals')
            
            vocals = sources[vocals_idx]
            no_vocals = 0
            for i, stem in enumerate(sources):
                if i != vocals_idx:
                    no_vocals += stem
            
            out_path = os.path.join(output_dir, "separated", MODEL_NAME, taskId)
            os.makedirs(out_path, exist_ok=True)
            
            vocals_file = os.path.join(out_path, "vocals.mp3")
            instr_file = os.path.join(out_path, "no_vocals.mp3")
            
            save_audio(vocals.cpu(), vocals_file, samplerate=self.model.samplerate, bitrate=320)
            save_audio(no_vocals.cpu(), instr_file, samplerate=self.model.samplerate, bitrate=320)
            
            print(f"[worker] Finished {taskId}")
            return {"success": True, "instrumentalPath": instr_file}
        except Exception as e:
            print(f"[worker] Error: {e}")
            return {"success": False, "error": str(e)}

    def check_timeout(self):
        while self.running:
            time.sleep(60)
            if time.time() - self.last_active > INACTIVITY_TIMEOUT:
                print("[worker] Inactivity timeout reached. Shutting down.")
                self.running = False
                if os.path.exists(SOCKET_PATH):
                    os.remove(SOCKET_PATH)
                sys.exit(0)

    def run(self):
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
            
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        server.listen(10)
        server.settimeout(5)
        
        print(f"[worker] Listening on {SOCKET_PATH}")
        
        threading.Thread(target=self.check_timeout, daemon=True).start()
        
        while self.running:
            try:
                conn, _ = server.accept()
                with conn:
                    # Increase buffer size for potential multi-message reads
                    data = conn.recv(8192)
                    if not data:
                        continue
                    
                    try:
                        req = json.loads(data.decode())
                    except:
                        continue

                    if req.get("command") == "separate":
                        with self.lock:
                            result = self.separate(req["inputPath"], req["outputDir"], req["taskId"], conn)
                        conn.sendall(json.dumps(result).encode() + b"\n")
                    elif req.get("command") == "ping":
                        conn.sendall(json.dumps({"status": "ok"}).encode() + b"\n")
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[worker] Server error: {e}")
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[worker] Server error: {e}")

if __name__ == "__main__":
    worker = DemucsWorker()
    worker.run()
