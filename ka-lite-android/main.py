import os
from functools import partial
from collections import namedtuple, defaultdict
import kivy
kivy.require('1.8.0')
from kivy.properties import NumericProperty, StringProperty, ObjectProperty
from kivy.app import App
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from android.runnable import run_on_ui_thread
from android import AndroidService

import logging
logging.root = Logger

from jnius import autoclass, cast, PythonJavaClass, java_method
String = autoclass('java.lang.String')
Uri = autoclass('android.net.Uri')
Context = autoclass('android.content.Context')
Intent = autoclass('android.content.Intent')
Toast = autoclass('android.widget.Toast')
DialogInterface = autoclass('android.content.DialogInterface')
AlertDialogBuilder = autoclass('android.app.AlertDialog$Builder')
DownloadManager = autoclass('android.app.DownloadManager')
DownloadManagerRequest = autoclass('android.app.DownloadManager$Request')
DownloadManagerQuery = autoclass('android.app.DownloadManager$Query')


def start_activity(intent):
    activity = autoclass('org.renpy.android.PythonActivity').mActivity
    activity.startActivity(intent)


def make_toast(text, duration=5):
    activity = autoclass('org.renpy.android.PythonActivity').mActivity
    toast = Toast.makeText(activity, String(text), duration)
    toast.show()


def get_download_manager():
    activity = autoclass('org.renpy.android.PythonActivity').mActivity
    return cast('android.app.DownloadManager',
                activity.getSystemService(Context.DOWNLOAD_SERVICE))


def get_content_uri(name):
    return Uri.parse(
        '/'.join(('file:/', os.path.abspath('.'), 'content', name)))


class AppLayout(GridLayout):
    pass


class DownloadProgress(BoxLayout):
    download_id = NumericProperty()
    destination = StringProperty('')
    status = ObjectProperty()

    def __init__(self, download_id, destination):
        super(DownloadProgress, self).__init__()
        self.download_id = download_id
        self.destination = destination

    def progress_string(self, destination, status):
        status_string = status.status or ''
        return "{status} download of {name}: {downloaded} of {total} ({progress}%)".format(
            status=status_string.capitalize(), name=destination,
            downloaded=status.downloaded, total=status.total,
            progress=status.progress)


class OnClickListener(PythonJavaClass):

    __javainterfaces__ = ['android/content/DialogInterface$OnClickListener']

    def __init__(self, callback, *args, **kwargs):
        super(OnClickListener, self).__init__(*args, **kwargs)
        self.callback = callback

    @java_method('(Landroid/content/DialogInterface;I)V')
    def onClick(self, dialog, which):
        self.callback(confirmed=(which == DialogInterface.BUTTON_POSITIVE))


ProgressStatus = namedtuple('ProgressStatus',
                            'downloaded total progress status')


def get_downloads_progress(*download_ids):
    manager = get_download_manager()
    query = DownloadManagerQuery()
    query.setFilterById(*download_ids)
    cursor = manager.query(query)

    def column_index(name):
        return cursor.getColumnIndex(getattr(DownloadManager, name))

    column_names = ('COLUMN_ID', 'COLUMN_BYTES_DOWNLOADED_SO_FAR',
                    'COLUMN_TOTAL_SIZE_BYTES', 'COLUMN_STATUS')
    ID, DOWNLOADED, TOTAL, STATUS = map(column_index, column_names)

    def status_string(status_id):
        statuses = {DownloadManager.STATUS_FAILED: 'failed',
                    DownloadManager.STATUS_PAUSED: 'paused',
                    DownloadManager.STATUS_PENDING: 'pending',
                    DownloadManager.STATUS_RUNNING: 'running',
                    DownloadManager.STATUS_SUCCESSFUL: 'successful'}
        return statuses.get(status_id, None)

    while True:
        progress = defaultdict(lambda: ProgressStatus(0, 0, 0, None))
        data_available = cursor.moveToFirst()
        while data_available:
            downloaded = cursor.getInt(DOWNLOADED)
            total = cursor.getInt(TOTAL)
            if total < 0:
                downloaded = total = 0
            progress[cursor.getInt(ID)] = ProgressStatus(
                downloaded,
                total,
                (downloaded * 100) / (total or 1),
                status_string(cursor.getInt(STATUS)))
            data_available = cursor.moveToNext()
        cursor.close()
        yield progress
        cursor = manager.query(query)


class KALiteApp(App):

    server_host = '0.0.0.0'
    # choose a non-default port,
    # to avoid messing with other KA Lite installations
    server_port = '8032'

    urls = {
        'add_sub.mp4': 'http://s3.amazonaws.com/KA-youtube-converted/AuX7nPBqDts.mp4/AuX7nPBqDts.mp4',
        'add_sub.png': 'http://s3.amazonaws.com/KA-youtube-converted/AuX7nPBqDts.mp4/AuX7nPBqDts.png',
        'add_sub.srt': 'http://video.google.com/timedtext?lang=en&format=srt&v=AuX7nPBqDts'
        }

    downloads_current_progress = ObjectProperty()

    @property
    def video_is_available(self):
        return os.path.exists('content/completed')

    def build(self):
        self.layout = AppLayout()
        return self.layout

    def on_start(self):
        pass

    def on_pause(self):
        return True

    def on_stop(self):
        pass

    @run_on_ui_thread
    def show_browser(self):
        self.service = AndroidService('KA Lite', 'server is running')
        self.service.start(self.server_port)

        url = "http://127.0.0.1:{port}/exercises/addition_1.html".format(
            port=self.server_port)
        intent = Intent()
        intent.setAction(Intent.ACTION_VIEW)
        intent.setData(Uri.parse(url))
        start_activity(intent)

    @run_on_ui_thread
    def show_video(self):
        if not self.video_is_available:
            return self.ask_download_video()
        intent = Intent()
        intent.setAction(Intent.ACTION_VIEW)
        intent.setDataAndType(get_content_uri('add_sub.mp4'), 'video/*')
        #intent.setType('video/*')
        start_activity(intent)

    @run_on_ui_thread
    def delete_video(self):
        files = os.listdir('content')
        if files:
            [os.remove(os.path.join('content', f)) for f in files]
            make_toast("Video deleted successfully")
            self.video_icon_path = ''
        else:
            make_toast("Video is not exists")

    def ask_download_video(self):
        activity = autoclass('org.renpy.android.PythonActivity').mActivity
        builder = AlertDialogBuilder(activity)
        builder.setTitle(String('Video is not available'))
        builder.setMessage(String('Download exersice video an subtitles?'))
        listener = OnClickListener(self.download_video)
        builder.setPositiveButton(String('Yes'), listener)
        builder.setNegativeButton(String('No'), listener)
        builder.show()

    @run_on_ui_thread
    def download_video(self, confirmed=True):
        if not confirmed:
            return
        downloads = [(self.start_download(url, name), name) for name, url in
                     self.urls.iteritems()]
        self.watch_downloads(downloads, on_completed=self.show_video)

    def start_download(self, url, destination_name):
        manager = get_download_manager()
        request = DownloadManagerRequest(Uri.parse(url))

        if not os.path.exists('content'):
            os.makedirs('content')

        request.setDestinationUri(get_content_uri(destination_name))
        return manager.enqueue(request)

    def watch_downloads(self, downloads, on_completed=None):

        def add_progress(task):
            download_id, destination = task
            content.add_widget(DownloadProgress(download_id, destination))
            return download_id

        content = BoxLayout(orientation='vertical')
        download_ids = map(add_progress, downloads)
        popup = Popup(title='Downloading', content=content)
        popup.open()
        self.update_progress(popup, get_downloads_progress(*download_ids),
                             on_completed)

    def update_progress(self, popup, get_progress, on_completed, *args):
        progress = get_progress.next()
        self.downloads_current_progress = progress
        if all([status.status == 'successful' for status in progress.values()]):
            popup.dismiss()
            self.layout.do_layout()
            open('content/completed', 'a').close()
            self.video_icon_path = 'content/add_sub.png'
            if on_completed:
                on_completed()
        else:
            interval = 2
            Clock.schedule_once(partial(self.update_progress, popup,
                                        get_progress, on_completed),
                                interval)


if __name__ == '__main__':
    try:
        KALiteApp().run()
    except Exception as e:
        msg = "Error: {type}{args}".format(type=type(e),
                                           args=e.args)
        Logger.exception(msg)
        raise
