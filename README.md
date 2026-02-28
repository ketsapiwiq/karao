# karao

Génération MIDI Multi-pistes (Demucs + SwiftF0)

Ce pipeline permet de séparer un fichier audio en plusieurs pistes (voix, batterie, basse, guitare, piano, autre) et de générer un fichier MIDI multi-pistes.

    source venv/bin/activate
    venv/bin/pip install demucs swift-f0 librosa pretty_midi unidecode
    python3 multi_track_gen.py <fichier_audio> [-m htdemucs_6s] [-d cpu|cuda]
