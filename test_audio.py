"""Diagnóstico de áudio do JARVIS — rode com: python test_audio.py"""
import asyncio, os, queue, sys, tempfile
import numpy as np
import sounddevice as sd

# ── TTS ───────────────────────────────────────────────────────────────────────
print("=" * 50)
print("TESTE 1 — TTS (você deve ouvir uma frase)")
print("=" * 50)
try:
    import edge_tts, miniaudio

    async def _falar():
        c = edge_tts.Communicate(
            "JARVIS online. Teste de voz bem-sucedido.",
            "pt-BR-AntonioNeural",
            rate="+15%",
        )
        fd, tmp = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        await c.save(tmp)
        dec = miniaudio.decode_file(
            tmp,
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1,
            sample_rate=22050,
        )
        samples = np.frombuffer(dec.samples, dtype=np.float32).copy()
        os.unlink(tmp)
        print(f"  Amostras geradas: {len(samples)} | pico: {np.max(np.abs(samples)):.3f}")
        sd.play(samples, samplerate=22050, blocking=True)
        print("  [OK] TTS funcionando")

    asyncio.run(_falar())

except Exception as e:
    print(f"  [ERRO] TTS: {e}")

# ── Microfone ─────────────────────────────────────────────────────────────────
print()
print("=" * 50)
print("TESTE 2 — Microfone + Whisper (fale algo em 5 segundos)")
print("=" * 50)
try:
    import whisper

    q: queue.Queue[np.ndarray] = queue.Queue()

    def _cb(indata, frames, t, status):
        if status:
            print(f"  aviso sounddevice: {status}")
        q.put(indata[:, 0].copy())

    chunks = []
    print("  Gravando 5 segundos... FALE AGORA")
    with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                        blocksize=1024, callback=_cb):
        for _ in range(int(5 * 16000 / 1024)):
            chunks.append(q.get())

    audio = np.concatenate(chunks)
    pico = np.max(np.abs(audio))
    print(f"  Amostras gravadas: {len(audio)} | pico: {pico:.4f}")

    if pico < 0.001:
        print("  [AVISO] Sinal muito baixo — microfone pode não estar funcionando")
    else:
        print("  [OK] Microfone captando áudio")

    print("  Carregando Whisper e transcrevendo...")
    model = whisper.load_model("base")
    result = model.transcribe(audio, language="pt", fp16=False)
    texto = result["text"].strip()
    print(f"  Transcrição: '{texto}'")
    if texto:
        print("  [OK] STT funcionando")
    else:
        print("  [AVISO] Nenhum texto detectado")

except Exception as e:
    print(f"  [ERRO] Microfone/STT: {e}")

# ── Dispositivos disponíveis ───────────────────────────────────────────────────
print()
print("=" * 50)
print("DISPOSITIVOS DE ÁUDIO DISPONÍVEIS")
print("=" * 50)
try:
    devices = sd.query_devices()
    default_in  = sd.query_devices(kind="input")["name"]
    default_out = sd.query_devices(kind="output")["name"]
    print(f"  Entrada padrão : {default_in}")
    print(f"  Saída padrão   : {default_out}")
except Exception as e:
    print(f"  [ERRO] ao listar dispositivos: {e}")

print()
print("Diagnóstico concluído.")
