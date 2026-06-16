import subprocess
import os
import logging

logger = logging.getLogger("app.services.ffmpeg_engine")

class FFmpegEngine:
    @staticmethod
    def stitch_scenes(video_paths: list, voiceover_path: str, output_path: str):
        """
        Stitch multiple video clips with a voiceover audio track.
        Raises CalledProcessError with detailed stderr on FFmpeg failure.
        """
        if not video_paths:
            raise ValueError("No video clips available to merge.")

        # 1. Validate that all input files exist
        for path in video_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Video clip not found: {path}")
        if not os.path.exists(voiceover_path):
            raise FileNotFoundError(f"Voiceover file not found: {voiceover_path}")

        # 2. Use an absolute path for the concat list file
        list_file_path = os.path.abspath("clips.txt")
        with open(list_file_path, "w") as f:
            for path in video_paths:
                abs_path = os.path.abspath(path)
                f.write(f"file '{abs_path}'\n")

        try:
            # 3. Build the FFmpeg command with explicit stream mapping
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", list_file_path,  # Input 0 (Stitched Videos)
                "-i", voiceover_path,                                 # Input 1 (Voiceover Audio)
                
                # 🎯 TOPOLOGY STREAM MAPS
                "-map", "0:v:0",  # Extract ONLY the video track from the stitched clips (ignores cartoon audio)
                "-map", "1:a:0",  # Extract ONLY the audio track from the voiceover asset
                
                # Codecs & Rendering settings
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",  # Forces high pixel compatibility for browsers and media players
                "-c:a", "aac",          # Encodes voiceover safely into video-ready AAC format
                "-b:a", "192k",         # Ensures clean sound bitrate
                "-shortest",            # Cuts off any dangling video frames if audio finishes slightly earlier
                output_path
            ]

            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")

            # 4. Run with capture_output to get stderr
            result = subprocess.run(cmd, capture_output=True, text=True)

            # 5. If FFmpeg failed, log the actual error and raise detailed exception
            if result.returncode != 0:
                logger.error(f"FFmpeg exited with code {result.returncode}")
                logger.error(f"FFmpeg stderr:\n{result.stderr}")
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stderr
                )

            logger.info(f"Successfully created final video with audio track: {output_path}")

        finally:
            # Clean up temporary concat list file
            if os.path.exists(list_file_path):
                os.remove(list_file_path)