from typing import List
from instagrapi import Client
from instagrapi.types import Media, Resource
from pydantic_core import Url
from dotenv import load_dotenv
import frontmatter
import datetime
import os
import requests
from tqdm import tqdm

load_dotenv()

LOGIN_USERNAME = os.getenv('LOGIN_USERNAME')
LOGIN_PASSWORD = os.getenv('LOGIN_PASSWORD')

ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(ROOT_PATH, '_config.yml')
POSTS_FOLDER = os.path.join(ROOT_PATH, '_posts')
MEDIA_FOLDER = os.path.join(ROOT_PATH, 'media')

IG_USERNAME = "<YOUR-INSTAGRAM-USERNAME>" # Change and add your Instagram Account
IG_USERID = "<YOUR-INSTAGRAM-USER-PK>" # Add your Instagram PK, if can't set it to None i.e. IG_USERID = None

class Instagram:
    def __init__(self) -> None:
        self.cl: Client = Client()
        self.cl.login(LOGIN_USERNAME, LOGIN_PASSWORD)

    def get_media(self) -> List[Media]:
        self.medias: List[Media] = []
        if IG_USERID is not None:
            self.medias: List[Media] = self.cl.user_medias(user_id=IG_USERID)
        else:
            user_id = self.cl.user_id_from_username(IG_USERNAME)
            self.medias: List[Media] = self.cl.user_medias(user_id=user_id)

        return self.medias
    
    def media_in_posts_format(self) -> List["Post"]:
        if not hasattr(self, 'medias'):
            self.get_media()

        self.posts: List["Post"] = []

        for media in self.medias:
            self.posts.append(
                Post.from_ig_media(media)
            )

        return self.posts
        

class ArchivePostFile:
    def __init__(self, file_path: str, post: frontmatter.Post | None = None) -> None:
        self.file_path = file_path
        self.post = post
    
    def read_file(self) -> None:        
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"{self.file_path} is missing.")
        
        self.post = frontmatter.load(self.file_path)
    
    def save_file(self) -> None:
        if os.path.exists(self.file_path):
            raise FileExistsError(f"{self.file_path} already exists.")
        
        with open(self.file_path, "w") as file:
            file.write(frontmatter.dumps(self.post))

class Archive:
    def __init__(self) -> None:

        if not os.path.exists(CONFIG_FILE):
            raise FileNotFoundError('_config.yml file is missing.')

        if not os.path.exists(POSTS_FOLDER):
            raise FileNotFoundError('_posts/ directory is missing.')
        
        if not os.path.exists(MEDIA_FOLDER):
            os.mkdir(MEDIA_FOLDER)
        

    def get_files(self) -> List[ArchivePostFile]:
        self.archive_files: List[ArchivePostFile] = []

        post_files = os.listdir(POSTS_FOLDER)

        for file in post_files:
            if file.endswith('.md'):
                apf = ArchivePostFile(file_path = os.path.join(POSTS_FOLDER, file))
                apf.read_file()
                self.archive_files.append(apf)
            
        return self.archive_files
    
    def files_in_post_format(self) -> List["Post"]:
        if not hasattr(self, 'archive_files'):
            self.get_files()
        
        self.posts: List["Post"] = []

        for archive_file in self.archive_files:
            self.posts.append(
                Post.from_archive_files(
                    archive_file
                )
            )

        return self.posts
    
class PostMediaDownloadException(Exception):
    pass    
    
class PostMedia:
    def __init__(self, id: int, media_type: str, url: Url | None = None, local_url: str | None = None):
        self.id = id
        self.type = media_type
        self.url = url
        self.local_url = local_url

    @classmethod
    def from_resource(cls, resource: Resource):
        id = resource.pk
        if resource.media_type == 1:
            media_type = 'image'
            url = resource.thumbnail_url
        else:
            media_type = 'video'
            url = resource.video_url

        return cls(id, media_type, url, None)
    
    @classmethod
    def from_archive_file_media_dict(cls, media_dict: dict):
        id = media_dict['id']
        media_type = media_dict['type']
        url = media_dict['url']

        return cls(id, media_type, None, url)
    
    def is_downloaded(self) -> bool:
        if self.local_url is None:
            return False
        
        if not os.path.exists(self.local_url):
            raise FileNotFoundError(f"PostMedia {self.id}: {self.local_url} not found.")
        
        return True
    
    def download_media(self, post_id_dir_path: str) -> None:
        if self.is_downloaded():
            return
            
        if self.type == 'image':
            file_path = f"{self.id}.jpg"
            file_abs_path = os.path.join(post_id_dir_path, file_path)

            download_response = PostMedia.download_image(file_abs_path, self.url)

        else:
            file_path = f"{self.id}.mp4"
            file_abs_path = os.path.join(post_id_dir_path, file_path)

            download_response = PostMedia.download_video(file_abs_path, self.url)

        if download_response:
            self.local_url = os.path.relpath(file_abs_path, ROOT_PATH)
        else:
            raise PostMediaDownloadException(f"Error! {file_abs_path} could not be downloaded.")


    @staticmethod
    def download_image(file_path, url) -> bool:
        try:
            response = requests.get(url)
            response.raise_for_status()

            with open(file_path, 'wb') as file:
                file.write(response.content)

            return True
        except requests.exceptions.RequestException:
            return False
        
    @staticmethod
    def download_video(file_path, url) -> bool:
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            with open(file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)

            return True
        except requests.exceptions.RequestException:
            return False
    
class Post:
    def __init__(
        self,
        id: int,
        title: str,
        date: datetime.date,
        archive_date: datetime.date,
        thumbnail: PostMedia,
        media: List[PostMedia],
        permalink: str,
        caption: str,
        code: str
    ) -> None:
        self.id = id
        self.title = title
        self.date = date
        self.archive_date = archive_date
        self.thumbnail = thumbnail
        self.media = media
        self.permalink = permalink
        self.caption = caption
        self.code = code

    @property
    def is_archived(self) -> bool:
        return self.archive_date is not None
    
    @property
    def is_album(self) -> bool:
        return len(self.media) > 0
    
    @classmethod
    def from_ig_media(cls, ig_media: Media):
        id = ig_media.pk
        date = ig_media.taken_at
        caption = ig_media.caption_text
        permalink = f"/p/{ig_media.code}/"
        media = []
        title = f" by {IG_USERNAME}"
        code = ig_media.code

        if ig_media.media_type == 8:
            title = "Album" + title
            media = []
            for resource in ig_media.resources:
                media.append(PostMedia.from_resource(resource))
            thumbnail = PostMedia(id, 'image', url=ig_media.resources[0].thumbnail_url)

        elif ig_media.media_type == 2:
            title = "Video" + title
            media = [PostMedia(id, 'video', url=ig_media.video_url),]
            thumbnail = PostMedia(id, 'image', url=ig_media.thumbnail_url)
        else:
            title = "Image" + title
            media = [PostMedia(id, 'image', url=ig_media.thumbnail_url),]
            thumbnail = PostMedia(id, 'image', url=ig_media.thumbnail_url)
        
        return cls(id, title, date, None, thumbnail, media, permalink, caption, code)
    
    @classmethod
    def from_archive_files(cls, archive_file: ArchivePostFile):
        id = archive_file.post.metadata['id']
        title = archive_file.post.metadata['title']
        date = archive_file.post.metadata['date']
        archive_date = archive_file.post.metadata['archive_date']
        permalink = archive_file.post.metadata['permalink']
        caption = archive_file.post.content
        thumbnail = PostMedia(id, 'image', local_url=archive_file.post['thumbnail'])
        code = archive_file.post.metadata['code']

        media = []
        for media_dict in archive_file.post['media']:
            media.append(
                PostMedia.from_archive_file_media_dict(media_dict)
            )

        return cls(id, title, date, archive_date, thumbnail, media, permalink, caption, code)
    
    def download_media(self) -> bool:
        download_folder = os.path.join(ROOT_PATH, MEDIA_FOLDER, f"{self.code}")

        if not os.path.exists(download_folder):
            os.mkdir(download_folder)

        try:
            for media in self.media:
                media.download_media(download_folder)

            self.thumbnail.download_media(download_folder)

            return True
        except PostMediaDownloadException:
            return False
            

    def archive_post(self) -> bool:
        if self.is_archived:
            return False

        if not self.download_media():
            return False
        
        content = self.caption.replace("\n", "  \n")

        fm_post = frontmatter.Post(content)
        self.archive_date = datetime.date.today()

        fm_post['layout'] = 'post'
        fm_post['id'] = self.id
        fm_post['title'] = self.title
        fm_post['date'] = self.date
        fm_post['thumbnail'] = self.thumbnail.local_url
        fm_post['code'] = self.code

        fm_post['media'] = []

        for media in self.media:
            fm_post['media'].append(
                {
                    'id': media.id,
                    'type': media.type,
                    'url': media.local_url,
                }
            )

        fm_post['permalink'] = self.permalink
        fm_post['archive_date'] = self.archive_date

        fm_post_file_name = f"{self.date:%Y-%m-%d}-{self.code}.md"

        fm_post_file_path = os.path.join(POSTS_FOLDER, fm_post_file_name)

        try:
            archive_post_file = ArchivePostFile(
                file_path=fm_post_file_path,
                post=fm_post
            )
            archive_post_file.save_file()
        except:
            self.archive_date = None
            return False
        
        return True
    
    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Post):
            return False
        
        return self.id == value.id
    
    def __hash__(self):
        return hash(self.id)


def main():
    print("Instagram Posts Archiver")
    print("========================")

    print("\nLogging In to Instagram Account")
    ig = Instagram()
    ig_posts = ig.media_in_posts_format()

    print(f"\nInstagram Archive Account Username: {IG_USERNAME}")
    print(f"Instagram Archive Account UserId: {IG_USERID}")

    print(f"Total Post Count on Instagram: {len(ig_posts)}")

    archive = Archive()
    archived_posts = archive.files_in_post_format()

    print(f"\nNo. of Posts already archived: {len(archived_posts)}")

    to_be_archived_posts = list(set(ig_posts) - set(archived_posts))

    print(f"\nNo. of Posts to be archived: {len(to_be_archived_posts)}")

    print("Downloading to be archived posts: ")

    count = 0

    for post in tqdm(to_be_archived_posts, unit="post"):
        flag = post.archive_post()

        if flag: 
            count += 1

    print("Complete.")

if __name__ == "__main__":
    main()
