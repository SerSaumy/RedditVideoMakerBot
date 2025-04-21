import json
import random
import re
import os
from pathlib import Path
from random import randrange
from typing import Any, Dict, Tuple

import yt_dlp
from moviepy.editor import AudioFileClip, VideoFileClip
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from pydub import AudioSegment

from utils import settings
from utils.console import print_step, print_substep


def load_background_options():
    background_options = {}
    # Load background videos
    with open("./utils/background_videos.json") as json_file:
        background_options["video"] = json.load(json_file)

    # Load background audios
    with open("./utils/background_audios.json") as json_file:
        background_options["audio"] = json.load(json_file)

    # Remove "__comment" from backgrounds
    del background_options["video"]["__comment"]
    del background_options["audio"]["__comment"]

    for name in list(background_options["video"].keys()):
        pos = background_options["video"][name][3]

        if pos != "center":
            background_options["video"][name][3] = lambda t: ("center", pos + t)

    return background_options


def get_start_and_end_times(video_length: int, length_of_clip: int) -> Tuple[int, int]:
    """Generates a random interval of time to be used as the background of the video.

    Args:
        video_length (int): Length of the video
        length_of_clip (int): Length of the video to be used as the background

    Returns:
        tuple[int,int]: Start and end time of the randomized interval
    """
    initialValue = 180
    # Issue #1649 - Ensures that will be a valid interval in the video
    while int(length_of_clip) <= int(video_length + initialValue):
        if initialValue == initialValue // 2:
            raise Exception("Your background is too short for this video length")
        else:
            initialValue //= 2  # Divides the initial value by 2 until reach 0
    random_time = randrange(initialValue, int(length_of_clip) - int(video_length))
    return random_time, random_time + video_length


def get_background_config(mode: str):
    """Fetch the background/s configuration"""
    try:
        choice = str(settings.config["settings"]["background"][f"background_{mode}"]).casefold()
    except AttributeError:
        print_substep("No background selected. Picking random background'")
        choice = None

    # Handle default / not supported background using default option.
    # Default : pick random from supported background.
    if not choice or choice not in background_options[mode]:
        choice = random.choice(list(background_options[mode].keys()))

    return background_options[mode][choice]


def download_background_video(background_config: Tuple[str, str, str, Any]):
    """Downloads the background/s video from YouTube."""
    Path("./assets/backgrounds/video/").mkdir(parents=True, exist_ok=True)
    # note: make sure the file name doesn't include an - in it
    uri, filename, credit, _ = background_config
    if Path(f"assets/backgrounds/video/{credit}-{filename}").is_file():
        return
    print_step(
        "We need to download the backgrounds videos. they are fairly large but it's only done once. 😎"
    )
    print_substep("Downloading the backgrounds videos... please be patient 🙏 ")
    print_substep(f"Downloading {filename} from {uri}")
    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]",
        "outtmpl": f"assets/backgrounds/video/{credit}-{filename}",
        "retries": 10,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(uri)
    print_substep("Background video downloaded successfully! 🎉", style="bold green")


def download_background_audio(background_config: Tuple[str, str, str]):
    """Downloads the background/s audio from YouTube."""
    Path("./assets/backgrounds/audio/").mkdir(parents=True, exist_ok=True)
    # note: make sure the file name doesn't include an - in it
    uri, filename, credit = background_config
    if Path(f"assets/backgrounds/audio/{credit}-{filename}").is_file():
        return
    print_step(
        "We need to download the backgrounds audio. they are fairly large but it's only done once. 😎"
    )
    print_substep("Downloading the backgrounds audio... please be patient 🙏 ")
    print_substep(f"Downloading {filename} from {uri}")
    ydl_opts = {
        "outtmpl": f"./assets/backgrounds/audio/{credit}-{filename}",
        "format": "bestaudio/best",
        "extract_audio": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([uri])

    print_substep("Background audio downloaded successfully! 🎉", style="bold green")


def chop_background(bg_config: Dict[str, Any], tts_audio_path: str, reddit_object: dict):
    """
    Randomly selects a video and audio from the respective directories.
    Adjusts the duration to match the TTS audio length.
    """
    reddit_id = id(reddit_object)

    # Get the length of the TTS audio
    tts_audio = AudioSegment.from_file(tts_audio_path)
    tts_length = tts_audio.duration_seconds  # Length of TTS audio in seconds

    # Randomly select a video from the assets/backgrounds/video directory
    video_dir = "assets/backgrounds/video"
    video_files = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
    if not video_files:
        raise FileNotFoundError(f"No video files found in {video_dir}")
    video_choice = random.choice(video_files)  # Randomly select a video file

    # Ensure the output directory exists
    output_dir = f"assets/temp/{reddit_id}/"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Process background video
    with VideoFileClip(f"{video_dir}/{video_choice}") as video:
        max_start_time = max(0, video.duration - tts_length)
        start_time_video = random.uniform(0, max_start_time)
        end_time_video = start_time_video + tts_length
        new_video = video.subclip(start_time_video, end_time_video)
        new_video.write_videofile(f"{output_dir}background.mp4", codec="libx264")
    print_substep(f"Background video '{video_choice}' chopped successfully!", style="bold green")

    # Randomly select an audio file from the assets/backgrounds/audio directory
    audio_dir = "assets/backgrounds/audio"
    audio_files = [f for f in os.listdir(audio_dir) if f.endswith(".mp3")]
    if not audio_files:
        raise FileNotFoundError(f"No audio files found in {audio_dir}")
    audio_choice = random.choice(audio_files)  # Randomly select an audio file

    # Process background audio
    with AudioFileClip(f"{audio_dir}/{audio_choice}") as audio:
        max_start_time = max(0, audio.duration - tts_length)
        start_time_audio = random.uniform(0, max_start_time)
        end_time_audio = start_time_audio + tts_length
        new_audio = audio.subclip(start_time_audio, end_time_audio)
        new_audio.write_audiofile(f"{output_dir}background.mp3")
    print_substep(f"Background audio '{audio_choice}' chopped successfully!", style="bold green")


def mix_audio(tts_audio_path: str, background_audio_path: str, output_path: str):
    """
    Mixes TTS audio with background audio.
    """
    tts_audio = AudioSegment.from_file(tts_audio_path)
    background_audio = AudioSegment.from_file(background_audio_path).set_frame_rate(tts_audio.frame_rate).set_channels(tts_audio.channels)

    # Adjust background audio volume
    background_audio = background_audio - 15  # Reduce background audio volume

    # Overlay TTS audio on background audio
    mixed_audio = background_audio.overlay(tts_audio)

    # Export the mixed audio
    mixed_audio.export(output_path, format="mp3")


# Create a tuple for downloads background (background_audio_options, background_video_options)
background_options = load_background_options()
