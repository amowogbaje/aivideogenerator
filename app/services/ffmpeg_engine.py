import subprocess
import os

class FFmpegEngine:
    @staticmethod
    def stitch_scenes(video_paths: list, voiceover_path: str, output_path: str):
        if not video_paths:
            raise ValueError("No video clips available to merge.")

        # In production contexts, use file target listing chains to avoid system arg buffer exploits
        list_file_path = "clips.txt"
        with open(list_file_path, "w") as f:
            for path in video_paths:
                f.write(f"file '{os.path.abspath(path)}'\n")

        try:
            # Standard subprocess invocation to cleanly bind raw video clips with master vocal files
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", list_file_path,
                "-i", voiceover_path,
                "-c:v", "libx264", "-c:a", "aac", "-shortest",
                output_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            if os.path.exists(list_file_path):
                os.remove(list_file_path)