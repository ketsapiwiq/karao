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

    def separate(self, input_path, output_dir, taskId):
        self.load_model()
        self.last_active = time.time()
        
        # We'll use the demucs.separate logic but we want it to use our preloaded model
        # Actually, demucs.separate.main reloads the model. 
        # To truly warm up, we'd need to reimplement the separation logic here.
        # But wait, demucs has a cache for models. The bottleneck is often the first load 
        # and torch initialization. 
        
        # For simplicity and correctness, let's use the CLI-like call but within this persistent process
        # to keep the Python interpreter and torch warmed up.
        # To truly avoid reload, we need to call apply_model.
        
        try:
            # Re-implementing a minimal version of demucs.separate.main to use our preloaded model
            from demucs.audio import AudioFile
            from demucs.apply import apply_model
            import torch

            print(f"[worker] Separating {input_path}...")
            wav = AudioFile(input_path).read(streams=0, samplerate=self.model.samplerate, channels=self.model.audio_channels)
            wav = wav.to(next(self.model.parameters()).device)
            
            # Normalization
            ref = wav.mean(0)
            wav -= ref.mean()
            wav /= ref.std()

            sources = apply_model(self.model, wav[None], num_workers=1)[0]
            sources *= ref.std()
            sources += ref.mean()

            # Save stems
            # For karaoke we usually want vocals and no_vocals (instrumental)
            # htdemucs produces: drums, bass, other, vocals
            
            stem_names = self.model.sources
            vocals_idx = stem_names.index('vocals')
            
            # vocals
            vocals = sources[vocals_idx]
            
            # no_vocals (sum of everything except vocals)
            no_vocals = 0
            for i, stem in enumerate(sources):
                if i != vocals_idx:
                    no_vocals += stem
            
            # Match the API structure: DATA_DIR/separated/MODEL_NAME/taskId
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
        server.settimeout(5) # Allow periodic check of self.running
        
        print(f"[worker] Listening on {SOCKET_PATH}")
        
        threading.Thread(target=self.check_timeout, daemon=True).start()
        
        while self.running:
            try:
                conn, _ = server.accept()
                with conn:
                    data = conn.recv(4096)
                    if not data:
                        continue
                    
                    req = json.loads(data.decode())
                    if req.get("command") == "separate":
                        with self.lock:
                            result = self.separate(req["inputPath"], req["outputDir"], req["taskId"])
                        conn.sendall(json.dumps(result).encode())
                    elif req.get("command") == "ping":
                        conn.sendall(json.dumps({"status": "ok"}).encode())
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[worker] Server error: {e}")

if __name__ == "__main__":
    worker = DemucsWorker()
    worker.run()
