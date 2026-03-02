import os
import sys
import time
import socket
import json
import threading
import torch
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
                print("[worker] GPU (ROCm) detected! Moving model to GPU.")
                self.model.cuda()
            else:
                print("[worker] NO GPU DETECTED. Using CPU (this will be slow).")
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
            send_status("Reading audio file...", 15)
            wav = AudioFile(input_path).read(streams=0, samplerate=self.model.samplerate, channels=self.model.audio_channels)
            
            # Move data to the same device as the model
            device = next(self.model.parameters()).device
            wav = wav.to(device)
            
            send_status("Normalizing audio...", 25)
            ref = wav.mean(0)
            wav -= ref.mean()
            wav /= ref.std()

            duration = wav.shape[1] / self.model.samplerate
            send_status("Processing audio in segments...", 40)
            print(f"[worker] Audio shape: {wav.shape}, duration: {duration:.2f}s, device: {device}")
            
            segment_length = 30 # seconds
            total_segments = int(duration / segment_length) + 1
            
            all_sources = []
            for i in range(total_segments):
                start = i * segment_length * self.model.samplerate
                end = min((i + 1) * segment_length * self.model.samplerate, wav.shape[1])
                if start >= wav.shape[1]: break
                
                chunk = wav[:, start:end]
                print(f"[worker] Processing segment {i+1}/{total_segments} ({start}:{end})...")
                send_status(f"Separating segment {i+1}/{total_segments}...", 40 + int((i / total_segments) * 40))
                
                # Process chunk
                try:
                    # num_workers=0 to avoid subprocesses issues inside docker/socket
                    chunk_sources = apply_model(self.model, chunk[None], num_workers=0)[0] 
                    
                    # chunk_sources shape is [sources, channels, time]
                    print(f"[worker] Chunk {i+1} result shape: {chunk_sources.shape}, expected time: {chunk.shape[-1]}")

                    # Trim chunk_sources to match input chunk length if htdemucs padded it
                    if chunk_sources.shape[-1] > chunk.shape[-1]:
                        chunk_sources = chunk_sources[..., :chunk.shape[-1]]
                    elif chunk_sources.shape[-1] < chunk.shape[-1]:
                        # This shouldn't happen with htdemucs usually, but for safety:
                        print(f"[worker] WARNING: Chunk {i+1} is SHORTER than expected!")
                        
                    all_sources.append(chunk_sources)
                except Exception as e:
                    print(f"[worker] Error processing segment {i+1}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    raise e
            
            print(f"[worker] All segments processed. Concatenating {[s.shape for s in all_sources]} along dim=2...")
            sources = torch.cat(all_sources, dim=2) # Dim 2 is time in [sources, channels, time]

            send_status("Saving stems...", 85)
            print(f"[worker] Saving stems to disk...")
            stem_names = self.model.sources
            vocals_idx = stem_names.index('vocals')
            
            vocals = sources[vocals_idx]
            no_vocals = 0
            for i, stem in enumerate(sources):
                if i != vocals_idx:
                    no_vocals += stem
            
            out_path = os.path.join(output_dir, "separated", MODEL_NAME, taskId)
            os.makedirs(out_path, exist_ok=True)
            
            # save_audio expects CPU tensor
            save_audio(vocals.cpu(), os.path.join(out_path, "vocals.mp3"), samplerate=self.model.samplerate)
            save_audio(no_vocals.cpu(), os.path.join(out_path, "no_vocals.mp3"), samplerate=self.model.samplerate)
            
            print(f"[worker] Separation finished for {taskId}")
            return {"success": True}
        except Exception as e:
            print(f"[worker] Separation error for {taskId}: {str(e)}")
            import traceback
            traceback.print_exc()
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
                    data = conn.recv(8192)
                    if not data:
                        continue
                    
                    try:
                        req = json.loads(data.decode())
                    except:
                        continue

                    if req.get("command") == "separate":
                        self.last_active = time.time()
                        with self.lock:
                            result = self.separate(req["inputPath"], req["outputDir"], req["taskId"], conn)
                        conn.sendall(json.dumps(result).encode() + b"\n")
                    elif req.get("command") == "ping":
                        conn.sendall(json.dumps({"status": "ok"}).encode() + b"\n")
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[worker] Server error: {e}")

if __name__ == "__main__":
    worker = DemucsWorker()
    worker.run()
