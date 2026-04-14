import moviepy.editor as mpe

# Monkeypatch for compatibility
if not hasattr(mpe, 'AudioClip'):
    mpe.AudioClip = mpe.AudioClip
if not hasattr(mpe, 'VideoFileClip'):
    mpe.VideoFileClip = mpe.VideoFileClip

mpe.VideoFileClip.with_audio = mpe.VideoFileClip.set_audio
mpe.VideoFileClip.resized = mpe.VideoFileClip.resize
mpe.VideoFileClip.subclipped = mpe.VideoFileClip.subclip
mpe.AudioFileClip.subclipped = mpe.AudioFileClip.subclip
