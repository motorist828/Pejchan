# --- START OF FILE posts_bp.py ---

from flask import current_app, Blueprint, render_template, redirect, request, flash, session, url_for
# Use the updated database and moderation modules
from database_modules import database_module, moderation_module, formatting
from flask_socketio import SocketIO, emit
# Import datetime and timezone
from datetime import datetime, timezone
from PIL import Image, ImageSequence, UnidentifiedImageError
import cv2
import re
import os
import time
import shutil
import logging # Use logging
from werkzeug.utils import secure_filename # Useful for sanitizing original filenames
import random
import string

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Usually configured in main app
logger = logging.getLogger(__name__) # Use Flask's logger or configure one

# Blueprint register
posts_bp = Blueprint('posts', __name__, template_folder='../templates', static_folder='../static')
# SocketIO instance will be retrieved from current_app later

# --- Constants ---
THUMB_SIZE = (250, 250)
# Relative path to placeholder MP3 thumbnail within the static folder
MP3_THUMB_REL_PATH = 'play.jpg'
# Allowed file extensions (lowercase)
ALLOWED_EXTENSIONS = {'.jpeg', '.jpg', '.mov', '.gif', '.png', '.webp', '.webm', '.mp4', '.mp3'}
# Define upload folders relative to the static directory base
POST_IMAGE_FOLDER_REL = 'post_images'
REPLY_IMAGE_FOLDER_REL = 'reply_images'
MAX_COMMENT_LENGTH = 20000 # Example limit

# --- Helper Functions ---
def get_static_file_abs_path(relative_path):
    """Gets the absolute path for a file within the static folder."""
    try:
        # Use Flask's app context if available, otherwise assume script runs from root
        static_folder = current_app.static_folder if current_app else 'static'
        return os.path.join(static_folder, relative_path)
    except RuntimeError: # Outside of application context
        logger.warning("Cannot get current_app context for static folder. Assuming 'static' directory.")
        return os.path.join('static', relative_path)

# Get absolute path for MP3 placeholder
MP3_THUMB_ABS_PATH = get_static_file_abs_path(MP3_THUMB_REL_PATH)

# --- Post Handler Class ---
class PostHandler:
    # Use the managers from the updated moderation module
    timeout_manager = moderation_module.TimeoutManager()
    ban_manager = moderation_module.BanManager()

    def __init__(self, socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input):
        if socketio is None:
            logger.error("!!! PostHandler received socketio as None !!!")
        else:
            logger.info("--- PostHandler initialized with a valid socketio instance ---")
        self.socketio = socketio
        self.user_ip = user_ip
        self.post_mode = post_mode # "post" or "reply"
        # Sanitize/default post name
        raw_name = post_name.strip() if post_name else "Anonymous"
        # Filter XSS from name *before* generating tripcode or saving (assuming done in route)
        self.post_name = raw_name # Store the potentially tripcode-containing name
        self.board_id = board_id # This is the board_uri
        self.original_content = comment # Keep original for DB
        # Format comment for display/storage (assuming XSS filter was applied in route)
        self.comment = formatting.format_comment(comment)
        self.embed = embed # Embed URL (ensure validated/sanitized in route if needed)
        self.captcha_input = captcha_input
        self.embed = embed

    def check_banned(self):
        """Checks if the user's IP is banned using the BanManager."""
        try:
            banned_status = self.ban_manager.is_banned(self.user_ip)
            if banned_status.get('is_banned', False):
                reason = banned_status.get('reason', 'No reason provided.')
                flash(f"You are banned. Reason: {reason}", "error")
                logger.warning(f"Banned IP {self.user_ip} attempted to post. Reason: {reason}")
                return False # Banned
            return True # Not banned
        except Exception as e:
            logger.error(f"Error checking ban status for IP {self.user_ip}: {e}", exc_info=True)
            flash("An error occurred while checking ban status. Please try again later.", "error")
            return False # Fail safely (treat as banned)

    def check_timeout(self):
        """Checks if the user is under a posting timeout using TimeoutManager."""
        try:
            timeout_status = self.timeout_manager.check_timeout(self.user_ip)
            if timeout_status.get('is_timeout', False):
                flash("Please wait a few seconds before posting again.", "warning")
                logger.info(f"IP {self.user_ip} attempted to post while under timeout.")
                return False # Timed out
            return True # Not timed out
        except Exception as e:
            logger.error(f"Error checking timeout status for IP {self.user_ip}: {e}", exc_info=True)
            flash("An error occurred while checking posting timeout. Please try again later.", "error")
            return False # Fail safely

    def validate_comment(self):
        """Validates the comment length."""
        if len(self.original_content) > MAX_COMMENT_LENGTH:
            flash(f"Your comment is too long (max {MAX_COMMENT_LENGTH} characters).", "error")
            return False
        return True

    def generate_thumbnail(self, original_path, thumb_path, file_ext):
        """Generates a thumbnail for various file types."""
        try:
            logger.info(f"Generating thumbnail for {original_path} -> {thumb_path}")
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True) # Ensure thumb dir exists

            if file_ext in ['.jpeg', '.jpg', '.png', '.webp']:
                with Image.open(original_path) as img:
                    # Check orientation EXIF tag and rotate if necessary
                    try:
                        # Find Orientation tag number
                        for orientation_tag in Image.ExifTags.TAGS.keys():
                            if Image.ExifTags.TAGS[orientation_tag] == 'Orientation':
                                break
                        else:
                             orientation_tag = None # Orientation tag not found

                        if orientation_tag:
                            exif_data = img._getexif()
                            if exif_data is not None:
                                orientation = exif_data.get(orientation_tag)
                                logger.debug(f"Image {original_path} EXIF Orientation: {orientation}")

                                if orientation == 3: img = img.rotate(180, expand=True)
                                elif orientation == 6: img = img.rotate(270, expand=True)
                                elif orientation == 8: img = img.rotate(90, expand=True)
                    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exif_err:
                        logger.warning(f"Could not process EXIF data for {original_path}: {exif_err}")
                        pass # Ignore if no EXIF data or orientation tag

                    img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                    save_format = 'JPEG'
                    quality = 85
                    img_mode = img.mode
                    # Check for transparency
                    has_transparency = (img_mode == 'RGBA' or
                                        (img_mode == 'P' and 'transparency' in img.info) or
                                        (img_mode == 'LA'))

                    if has_transparency:
                        save_format = 'PNG'
                        quality = None # PNG quality is handled differently (compression)
                        # Ensure conversion to RGBA if not already, to preserve transparency
                        if img_mode != 'RGBA':
                            img = img.convert('RGBA')
                    else:
                        # If no transparency, convert to RGB for JPEG saving
                        if img_mode != 'RGB':
                            img = img.convert('RGB')

                    # Save the thumbnail
                    save_kwargs = {'format': save_format}
                    if quality: save_kwargs['quality'] = quality
                    # Optimize PNG/JPEG output
                    if save_format == 'PNG': save_kwargs['optimize'] = True
                    if save_format == 'JPEG': save_kwargs['optimize'] = True; save_kwargs['progressive'] = True

                    img.save(thumb_path, **save_kwargs)

                logger.debug(f"Image thumbnail created: {thumb_path}")
                return True

            elif file_ext == '.gif':
                 try:
                     with Image.open(original_path) as img:
                        # Use ImageSequence to properly handle frames
                        frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
                        if not frames: raise ValueError("No frames found in GIF")

                        # Create thumbnail from the first frame
                        first_frame = frames[0]
                        first_frame.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)

                        # Decide output format: If animated GIF -> static PNG thumb, else maybe keep GIF thumb?
                        # For simplicity, always create a static PNG thumb from first frame
                        if first_frame.mode != 'RGBA':
                            first_frame = first_frame.convert('RGBA')
                        first_frame.save(thumb_path, format='PNG', optimize=True)
                        logger.debug(f"GIF thumbnail created (static PNG): {thumb_path}")
                        return True
                 except Exception as gif_err:
                      logger.error(f"Error processing GIF {original_path}: {gif_err}", exc_info=True)
                      return False

            elif file_ext in ['.mp4', '.mov', '.webm']:
                 success = self.capture_frame_from_video(original_path, thumb_path)
                 if success: logger.debug(f"Video thumbnail created: {thumb_path}")
                 else: logger.warning(f"Failed to create video thumbnail for {original_path}")
                 return success

            elif file_ext == '.mp3':
                if not os.path.exists(MP3_THUMB_ABS_PATH):
                    logger.warning(f"MP3 thumbnail placeholder not found at {MP3_THUMB_ABS_PATH}")
                    return False
                shutil.copy2(MP3_THUMB_ABS_PATH, thumb_path)
                logger.debug(f"MP3 thumbnail placeholder copied: {thumb_path}")
                return True

        except UnidentifiedImageError:
            logger.error(f"Cannot identify image file (corrupted or unsupported): {original_path}", exc_info=False)
            flash(f"Could not process image file '{os.path.basename(original_path)}'. It might be corrupted or in an unsupported format.", "error")
            return False
        except cv2.error as e:
             logger.error(f"OpenCV error processing video {original_path}: {e}", exc_info=True)
             flash(f"Could not process video file '{os.path.basename(original_path)}'.", "error")
             return False
        except Exception as e:
            # Catch other potential errors from PIL or filesystem operations
            logger.error(f"Error generating thumbnail for {original_path}: {e}", exc_info=True)
            flash(f"An unexpected error occurred while processing file '{os.path.basename(original_path)}'.", "error")
            return False
        # If file_ext was not handled
        logger.warning(f"Thumbnail generation not implemented for extension: {file_ext}")
        return False

    def capture_frame_from_video(self, video_path, thumb_path):
        """Captures a frame from video using OpenCV and saves as JPG thumbnail."""
        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Error: Unable to open video file: {video_path}")
                return False

            # Try to capture frame around 1 second mark, fallback to first frame
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            target_frame_idx = 0 # Default to first frame
            if fps and fps > 0 and total_frames > fps: # If video > 1 sec
                target_frame_idx = int(fps)

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
            ret, frame = cap.read()

            if not ret: # If failed at target frame, try first frame
                logger.warning(f"Failed to read frame at index {target_frame_idx} for {video_path}, trying frame 0.")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    logger.error(f"Error: Unable to read any frame from video: {video_path}")
                    return False

            # Convert frame to PIL Image
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)

            # Create thumbnail
            pil_image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)

            # Save as JPG
            pil_image.save(thumb_path, format='JPEG', quality=85, optimize=True, progressive=True)
            return True

        except cv2.error as e:
             logger.error(f"OpenCV processing error for video {video_path}: {e}", exc_info=True)
             return False
        except Exception as e:
             logger.error(f"Unexpected error capturing video frame for {video_path}: {e}", exc_info=True)
             return False
        finally:
            if cap:
                cap.release() # Ensure video file is released

    def process_uploaded_files(self, upload_folder_rel, is_thread=False):
        """
        Processes uploaded files: saves original with unique name, generates thumbnail.
        Returns list of dicts: [{'original': filename, 'thumbnail': rel_thumb_path}, ...] or None on critical error.
        """
        files = request.files.getlist('fileInput') # Get list of FileStorage objects
        processed_files_info = []

        # Determine absolute paths based on relative folder names
        static_folder_abs = get_static_file_abs_path('') # Get abs path to static folder
        original_folder_abs = os.path.join(static_folder_abs, upload_folder_rel)
        thumb_folder_abs = os.path.join(original_folder_abs, 'thumbs')

        # Ensure directories exist
        try:
            os.makedirs(original_folder_abs, exist_ok=True)
            os.makedirs(thumb_folder_abs, exist_ok=True)
        except OSError as e:
             logger.error(f"Failed to create upload directories: {e}", exc_info=True)
             flash("Server error: Could not create upload directory.", "error")
             return None # Indicate critical error

        for file in files:
            if file.filename == '':
                continue # Skip empty file inputs

            # Get original filename and extension safely
            original_filename_unsafe = file.filename
            _, file_ext = os.path.splitext(original_filename_unsafe)
            file_ext = file_ext.lower() # Ensure lowercase extension

            if file_ext not in ALLOWED_EXTENSIONS:
                flash(f"File type '{file_ext}' is not allowed for file '{original_filename_unsafe}'.", "warning")
                logger.warning(f"Disallowed file type '{file_ext}' uploaded by {self.user_ip}. Original name: {original_filename_unsafe}")
                continue # Skip this file

            # Generate unique filename using timestamp
            timestamp_ms = int(time.time() * 1000)
            unique_filename_base = str(timestamp_ms)
            # Add a random element for extremely unlikely collisions
            unique_filename_base += "_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            new_filename = f"{unique_filename_base}{file_ext}"

            original_save_path = os.path.join(original_folder_abs, new_filename)

            # Define thumbnail name and path
            thumb_ext = '.jpg' # Default thumbnail extension
            if file_ext == '.mp3': thumb_ext = '.jpg' # MP3 uses JPG placeholder
            elif file_ext == '.gif': thumb_ext = '.png' # Static PNG thumb for GIF
            elif file_ext in ['.png', '.webp']: thumb_ext = '.png' # Keep PNG for potential transparency

            thumb_filename = f"thumb_{unique_filename_base}{thumb_ext}"
            thumb_save_path = os.path.join(thumb_folder_abs, thumb_filename)

            try:
                # Save the original file
                file.save(original_save_path)
                logger.info(f"Saved original file: {original_save_path}")

                # Generate thumbnail
                if self.generate_thumbnail(original_save_path, thumb_save_path, file_ext):
                    # Construct the relative path for the thumbnail for DB/HTML
                    # Path should be relative to the *static* folder root
                    thumb_relative_path = os.path.join(upload_folder_rel, 'thumbs', thumb_filename).replace('\\', '/')

                    processed_files_info.append({
                        'original': new_filename,         # Just the filename for DB
                        'thumbnail': thumb_relative_path  # Relative path from static root
                    })
                else:
                    # Thumbnail generation failed, cleanup original file
                    logger.warning(f"Thumbnail generation failed for {new_filename}. Removing original file.")
                    os.remove(original_save_path)
                    # Flash message was likely set inside generate_thumbnail

            except Exception as e:
                logger.error(f"Error saving or processing file {original_filename_unsafe} as {new_filename}: {e}", exc_info=True)
                flash(f"Error processing file: {original_filename_unsafe}", "error")
                # Cleanup partially saved file if it exists
                if os.path.exists(original_save_path):
                    try: os.remove(original_save_path)
                    except OSError as rm_err: logger.error(f"Failed to cleanup partially saved file {original_save_path}: {rm_err}")

        # Final check: if comment is empty, we need at least one processed file
        if not self.comment and not processed_files_info:
             # This condition should primarily be checked in the route handlers
             # based on whether it's a post or reply, but added here as a safeguard.
             # flash message should be more specific in the route.
             logger.warning("Post attempt with no comment and no successfully processed files.")
             # Returning empty list might be better than None if some files were attempted but failed
             # return None
             pass # Let route handler decide based on processed_files_info length

        return processed_files_info # Return list (possibly empty)


    def handle_reply(self, reply_to_thread_id):
        """
        Handles creating a reply entry in the database and emitting socket event.
        Skips applying the standard timeout if self.embed contains the PASSCODE.
        Returns the ID of the new reply on success, None otherwise.
        """
        # Ensure reply_to_thread_id is an integer
        try:
            tid = int(reply_to_thread_id)
        except (ValueError, TypeError):
             flash("Invalid thread ID format.", "error")
             logger.error(f"Invalid thread ID received in handle_reply: {reply_to_thread_id}")
             return None # MODIFIED

        # Check if thread exists (using the correct DB function)
        if not database_module.check_replyto_exist(tid):
            flash("This thread doesn't exist!", "error")
            return None # MODIFIED

        # Check if thread is locked
        if database_module.verify_locked_thread(tid):
            flash("This thread is locked.", "error")
            return None # MODIFIED

        # Validate CAPTCHA if required for the board
        if database_module.verify_board_captcha(self.board_id):
            session_captcha = session.get('captcha_text')
            if not session_captcha:
                 flash("CAPTCHA session expired. Please refresh.", "warning")
                 logger.warning("CAPTCHA check failed: session data missing.")
                 return None # MODIFIED
            if not database_module.validate_captcha(self.captcha_input, session_captcha):
                flash("Invalid captcha.", "error")
                return None # MODIFIED

        # Process uploaded files
        processed_files = self.process_uploaded_files(REPLY_IMAGE_FOLDER_REL, is_thread=False)
        
        if processed_files is None: # Critical error during file processing
             return None # MODIFIED

        # Check: need either text or *successfully processed* file
        if not self.comment and not processed_files:
            flash("You need to type something or successfully upload a file for a reply.", "error")
            return None # MODIFIED

        # --- Prepare data for DB ---
        original_filenames = [f['original'] for f in processed_files]
        thumbnail_rel_paths = [f['thumbnail'] for f in processed_files] 

        # --- Add to Database ---
        new_reply_id = database_module.add_new_reply(
            self.user_ip,
            tid, 
            self.post_name, 
            self.comment, 
            self.embed, 
            original_filenames, 
            thumbnail_rel_paths 
        )

        if new_reply_id:
            try:
                socket_files_data = []
                for f_info in processed_files:
                    orig_url = url_for('static', filename=os.path.join(REPLY_IMAGE_FOLDER_REL, f_info['original'])).replace('\\', '/')
                    thumb_url = url_for('static', filename=f_info['thumbnail']).replace('\\', '/')
                    socket_files_data.append({'original': orig_url, 'thumbnail': thumb_url})

                now_utc = datetime.now(timezone.utc)
                now_display = database_module.format_datetime_for_display(now_utc)
                display_name = database_module.generate_tripcode(self.post_name)

                self.socketio.emit('nova_postagem', {
                    'type': 'New Reply',
                    'post': {
                        'id': new_reply_id, 
                        'reply_id': new_reply_id, 
                        'thread_id': tid,
                        'name': display_name, 
                        'content': self.comment, 
                        'files_data': socket_files_data, 
                        'date': now_display,
                        'board': self.board_id
                    }
                })
                logger.info(f"SocketIO 'nova_postagem' (New Reply) emitted for reply {new_reply_id}")

            except Exception as socket_err:
                 logger.error(f"Failed to emit SocketIO event for reply {new_reply_id}: {socket_err}", exc_info=True)

            PASSCODE = "passcode" 
            if self.embed != PASSCODE:
                self.timeout_manager.apply_timeout(self.user_ip, duration_seconds=35, reason="Automatic timeout after reply.")
                logger.info(f"Timeout applied for IP {self.user_ip} after reply {new_reply_id}.")
            else:
                logger.info(f"Timeout skipped for IP {self.user_ip} due to passcode in reply {new_reply_id}.")
            
            return new_reply_id # MODIFIED: Return the new reply ID
        else:
            flash("Failed to save reply to the database.", "error")
            return None # MODIFIED: Return None on DB failure


    def handle_post(self):
        """
        Handles creating a new thread entry in the database and emitting socket event.
        Returns the ID of the new post (thread OP) on success, None otherwise.
        """
        if database_module.verify_board_captcha(self.board_id):
            session_captcha = session.get('captcha_text')
            if not session_captcha:
                 flash("CAPTCHA session expired. Please refresh.", "warning")
                 logger.warning("CAPTCHA check failed: session data missing.")
                 return None # MODIFIED
            if not database_module.validate_captcha(self.captcha_input, session_captcha):
                flash("Invalid captcha.", "error")
                return None # MODIFIED

        processed_files = self.process_uploaded_files(POST_IMAGE_FOLDER_REL, is_thread=True)

        if processed_files is None: 
            return None # MODIFIED

        if not processed_files:
            flash("You need to successfully upload at least one file to start a thread.", "error")
            return None # MODIFIED
        
        if not self.comment and not processed_files:
             flash("You need to type something or upload a file.", "error")
             return None # MODIFIED

        original_filenames = [f['original'] for f in processed_files]
        thumbnail_rel_paths = [f['thumbnail'] for f in processed_files]

        new_post_id = database_module.add_new_post(
            self.user_ip,
            self.board_id,
            self.post_name,        
            self.original_content, 
            self.comment,          
            self.embed,
            original_filenames,
            thumbnail_rel_paths    
        )

        if new_post_id:
            try:
                socket_files_data = []
                for f_info in processed_files:
                    orig_url = url_for('static', filename=os.path.join(POST_IMAGE_FOLDER_REL, f_info['original'])).replace('\\', '/')
                    thumb_url = url_for('static', filename=f_info['thumbnail']).replace('\\', '/')
                    socket_files_data.append({'original': orig_url, 'thumbnail': thumb_url})

                now_utc = datetime.now(timezone.utc)
                now_display = database_module.format_datetime_for_display(now_utc)
                display_name = database_module.generate_tripcode(self.post_name)

                self.socketio.emit('nova_postagem', {
                    'type': 'New Thread',
                    'post': {
                        'id': new_post_id, 
                        'post_id': new_post_id, 
                        'name': display_name, 
                        'content': self.comment, 
                        'files_data': socket_files_data, 
                        'date': now_display,
                        'board': self.board_id,
                    }
                })
                logger.info(f"SocketIO 'nova_postagem' (New Thread) emitted for post {new_post_id}")

            except Exception as socket_err:
                 logger.error(f"Failed to emit SocketIO event for post {new_post_id}: {socket_err}", exc_info=True)

            self.timeout_manager.apply_timeout(self.user_ip, duration_seconds=35, reason="Automatic timeout after post.")
            return new_post_id # MODIFIED: Return the new post ID
        else:
            flash("Failed to save post to the database.", "error")
            return None # MODIFIED: Return None on DB failure

# --- Main Route for Handling Posts and Replies ---
@posts_bp.route('/new_post', methods=['POST'])
def new_post():
    socketio = current_app.extensions.get('socketio')
    if not socketio:
        logger.error("SocketIO instance not found in Flask app extensions!")
        flash("A server configuration error occurred (SocketIO).", "error")
        return redirect(request.referrer or url_for('boards.main_page'))
    else:
        logger.info("--- SocketIO instance obtained successfully in /new_post ---")

    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip: user_ip = user_ip.split(',')[0].strip()

    post_mode_form = request.form.get("post_mode", "post") 
    comment_raw = request.form.get('text', '').strip() 
    post_name_raw = request.form.get("name", "Anonymous").strip() 
    board_id = request.form.get('board_id') 
    embed = request.form.get('embed', '').strip()
    captcha_input = request.form.get('captcha', '').strip()
    thread_id_form = request.form.get('thread_id') 

    if not board_id:
        flash('Board ID is missing.', 'error')
        logger.warning(f"Post attempt failed: Board ID missing. IP: {user_ip}")
        return redirect(request.referrer or url_for('boards.main_page'))

    if not database_module.get_board_info(board_id):
         flash(f"Board '/{board_id}/' does not exist.", 'error')
         logger.warning(f"Post attempt failed: Board '{board_id}' not found. IP: {user_ip}")
         return redirect(url_for('boards.main_page'))

    captcha_required = database_module.verify_board_captcha(board_id)
    if captcha_required and not captcha_input:
        flash("Captcha is required for this board.", "error")
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    
    if formatting.filter_xss(comment_raw) or formatting.filter_xss(post_name_raw):
        flash('HTML tags are not allowed in name or comment.', 'error')
        logger.warning(f"Post attempt blocked due to potential XSS. IP: {user_ip}, Board: {board_id}")
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))

    handler = PostHandler(socketio, user_ip, post_mode_form, post_name_raw, board_id, comment_raw, embed, captcha_input)

    if not handler.check_banned():
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    if not handler.check_timeout():
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))

    if not handler.validate_comment():
         return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))

    is_reply_mode = False
    reply_to_thread_id = None

    if post_mode_form == "reply" and thread_id_form:
        try:
            reply_to_thread_id = int(thread_id_form)
            is_reply_mode = True
            logger.debug(f"Explicit reply mode detected. Replying to thread {reply_to_thread_id}")
        except (ValueError, TypeError):
            flash("Invalid thread ID provided for reply.", "error")
            logger.warning(f"Invalid thread_id '{thread_id_form}' in reply mode. IP: {user_ip}, Board: {board_id}")
            return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))

    reply_match = re.match(r'^(?:#|>>)(\d+)', comment_raw) 
    if not is_reply_mode and reply_match:
        potential_reply_target_id = int(reply_match.group(1))
        target_thread_id = database_module.get_thread_id_for_post(potential_reply_target_id)

        if target_thread_id:
            is_reply_mode = True
            reply_to_thread_id = target_thread_id
            logger.debug(f"Implicit reply mode detected via comment '{reply_match.group(0)}'. Replying to thread {reply_to_thread_id}")
            cleaned_comment = comment_raw[len(reply_match.group(0)):].lstrip()
            handler = PostHandler(socketio, user_ip, post_mode_form, post_name_raw, board_id, cleaned_comment, embed, captcha_input)
            if not handler.validate_comment():
                 return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
        else:
             flash(f"Cannot reply to post '{reply_match.group(0)}' as it doesn't exist.", "warning")
             logger.warning(f"Implicit reply failed: Target post '{reply_match.group(0)}' not found. IP: {user_ip}, Board: {board_id}")
             pass 

    # --- Execute Handler Logic ---
    posted_id = None # MODIFIED: To store the ID of the created post/reply
    
    if is_reply_mode:
        if reply_to_thread_id: 
            posted_id = handler.handle_reply(reply_to_thread_id)
        else:
             logger.error("Reply mode determined but reply_to_thread_id is missing.")
             flash("Internal error: Could not determine thread ID for reply.", "error")
             # posted_id remains None, will follow failure path
    else:
        posted_id = handler.handle_post()

    # --- Redirect based on success ---
    if posted_id: # MODIFIED: Check if an ID was returned (i.e., success)
        flash(f"Post successful! ID: {posted_id}", "success") # MODIFIED: Include ID in flash message
        
        if is_reply_mode and reply_to_thread_id:
             referrer_url = request.referrer
             if referrer_url:
                 base_url = referrer_url.split('#')[0]
                 # MODIFIED: Redirect to referrer (thread page) with an anchor to the new reply
                 return redirect(f"{base_url}#p{posted_id}")
             else:
                 # Fallback if referrer is not available
                 logger.warning("Referrer missing for reply redirect, falling back to board page.")
                 return redirect(url_for('boards.board_page', board_uri=board_id))
        else: # New thread
             try:
                # MODIFIED: Redirect to the new thread's page with an anchor.
                # Assumes a route named 'boards.thread_page' exists for viewing threads.
                # The new thread's ID (posted_id) is used as thread_id for the route.
                # The anchor #p<ID> points to the OP of the new thread.
                thread_redirect_url = url_for('boards.thread_page', board_uri=board_id, thread_id=posted_id, _anchor=f'p{posted_id}')
                return redirect(thread_redirect_url)
             except Exception as e: 
                logger.warning(
                    f"Could not build URL for thread view (board: {board_id}, thread: {posted_id}): {e}. "
                    "Falling back to board page redirect."
                )
                # Fallback to the board page if the specific thread URL cannot be constructed
                return redirect(url_for('boards.board_page', board_uri=board_id))
    else:
        # Handler failed, flash message should already be set by the handler
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))

# --- SocketIO Endpoint (Placeholder/Example) ---
# ... (rest of the file is unchanged)
# @posts_bp.route('/socket.io/')
# def socket_io_endpoint():
#     logger.debug("Received request to /socket.io/ endpoint (usually handled by library)")
#     return "Socket.IO Endpoint", 200

# --- END OF FILE posts_bp.py ---