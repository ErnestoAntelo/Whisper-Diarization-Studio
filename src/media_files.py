"""Shared media formats for selectors, folders, CLI and source lookup."""
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".wave", ".ogg", ".opus", ".flac", ".aac", ".wma", ".aif", ".aiff", ".m4b", ".amr", ".ac3", ".aiff", ".oga"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".mpeg", ".mpg", ".ts", ".mts", ".m2ts", ".3gp", ".flv", ".vob", ".ogv"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

def media_filetypes():
    patterns = lambda extensions: " ".join("*" + ext for ext in sorted(extensions))
    return [("Audio y vídeo", patterns(MEDIA_EXTENSIONS)), ("Audio", patterns(AUDIO_EXTENSIONS)),
            ("Vídeo", patterns(VIDEO_EXTENSIONS)), ("Todos los archivos (FFmpeg)", "*.*")]
