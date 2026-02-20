# Based on UltraSinger image (has demucs, librosa, pretty_midi, torch pre-installed)
FROM rakuri255/ultrasinger:latest

USER root

# Install swift-f0 for pitch detection
RUN pip install swift-f0

WORKDIR /karaokeke

COPY lrclib.py demucs.py swiftf0.py karagen.py kara.py midifile.py ./

CMD ["bash"]
