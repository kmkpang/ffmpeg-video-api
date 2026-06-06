import os
import io
import unittest
from unittest.mock import patch, MagicMock

# Set mock env variables before importing main to prevent errors
os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
os.environ["SUPABASE_KEY"] = "mock_key"

import main

class TestVideoBotLogic(unittest.TestCase):

    @patch("main.get_supabase_client")
    @patch("main.download_file")
    @patch("main.get_audio_duration")
    @patch("subprocess.run")
    def test_process_video_background_success(self, mock_run, mock_get_duration, mock_download, mock_supabase_client):
        # Setup mocks
        mock_get_duration.return_value = 15.0  # 15 seconds audio
        
        mock_supabase = MagicMock()
        mock_supabase_client.return_value = mock_supabase
        
        # Mock DB response
        mock_supabase.table().update().eq().execute.return_value = MagicMock()
        
        # Mock storage upload
        mock_supabase.storage.from_().upload.return_value = MagicMock()
        mock_supabase.storage.from_().get_public_url.return_value = "https://mock.supabase.co/storage/v1/object/public/videos/final.mp4"
        
        # Test inputs
        video_id = "test-video-uuid"
        image_urls = ["http://example.com/img1.jpg", "http://example.com/img2.jpg", "http://example.com/img3.jpg"]
        voice_audio_url = "http://example.com/audio.mp3"
        
        # Intercept builtins.open to bypass reading the non-existent final.mp4
        import builtins
        original_open = builtins.open
        
        def side_effect_open(file, mode='r', *args, **kwargs):
            if "final.mp4" in str(file) and 'r' in mode:
                return io.BytesIO(b"dummy video data")
            return original_open(file, mode, *args, **kwargs)
            
        with patch("builtins.open", side_effect_open):
            # Run function
            main.process_video_background(video_id, image_urls, voice_audio_url)
        
        # Verifications
        # 1. Verify audio duration was called
        mock_get_duration.assert_called_once()
        
        # 2. Verify downloads: 1 audio + 3 images = 4 downloads
        self.assertEqual(mock_download.call_count, 4)
        
        # 3. Verify database updates
        # Should update status to 'rendering' initially and 'completed' at the end
        self.assertEqual(mock_supabase.table.call_count, 3)
        
        # 4. Check FFMPEG commands run (3 segments + 1 concat + 1 merge = 5 calls)
        self.assertEqual(mock_run.call_count, 5)
        
        # Let's inspect the FFMPEG commands to verify zoompan direction alternations
        calls = mock_run.call_args_list
        # Call 0: Segment 0 (Zoom In)
        cmd_seg0 = calls[0][0][0]
        self.assertIn("zoompan=z='min(zoom+0.0008,1.25)'", cmd_seg0[7])  # Index 7 is -vf filter string
        # Call 1: Segment 1 (Zoom Out)
        cmd_seg1 = calls[1][0][0]
        self.assertIn("zoompan=z='max(1.25-0.0008*on,1.0)'", cmd_seg1[7])
        # Call 2: Segment 2 (Zoom In)
        cmd_seg2 = calls[2][0][0]
        self.assertIn("zoompan=z='min(zoom+0.0008,1.25)'", cmd_seg2[7])
        
        # Verify durations are correct
        # 15 seconds / 3 images = 5.0s per image
        self.assertEqual(cmd_seg0[11], "5.0")  # Index 11 is duration argument to -t
        self.assertEqual(cmd_seg1[11], "5.0")
        self.assertEqual(cmd_seg2[11], "5.0")

if __name__ == "__main__":
    unittest.main()
