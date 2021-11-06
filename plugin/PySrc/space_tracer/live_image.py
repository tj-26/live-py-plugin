import io
import sys
import typing
from abc import ABC, abstractmethod
from base64 import standard_b64encode
from pathlib import Path

from space_tracer.mock_turtle import MockTurtle

try:
    from PIL import Image
except ImportError:
    class Image:
        Image = None

Position = typing.Tuple[float, float]  # (x, y)
Size = typing.Tuple[int, int]  # (width, height)
Fill = typing.Tuple[int, int, int, int]  # (r, g, b, alpha)


class LiveImage(ABC):
    """ Display an image with live updates on the turtle canvas.

    To display any image format, create a subclass that converts your format to
    PNG bytes. See the Pillow Image version below as an example.
    """
    @abstractmethod
    def convert_to_png(self) -> bytes:
        """ Convert this image to bytes in PNG format.

        Override this method for any subclass to handle an image format.
        """
        pass

    def convert_to_painter(self) -> 'LivePainter':
        """ Convert this image to one that can be edited.

        Override this method if you don't want to depend on Pillow.
        """
        png_file = io.BytesIO(self.convert_to_png())
        image = Image.open(png_file)
        image.load()
        return LivePillowImage(image)

    def display(self, position: Position = None, align: str = 'topleft'):
        """ Display this image on the mock turtle's canvas.

        :param position: (x, y) coordinates on the canvas, or None for the
            top-left corner
        :param align: which point in the image to line up with (x, y) - a
            combination of 'top', 'center', or 'bottom' plus 'left', 'center', or
            'right'. If one of the words is missing, it defaults to 'center'.
        """

        png_bytes = self.convert_to_png()
        b64_bytes = standard_b64encode(png_bytes)
        b64_string = b64_bytes.decode('UTF-8')
        MockTurtle.display_image(b64_string, position, align)


class LivePainter(LiveImage):
    @abstractmethod
    def set_pixel(self, position: Position, fill: Fill):
        """ Set the colour of a pixel.

        :param position: the x and y coordinates of the pixel
        :param fill: the colour as a tuple of (red, green, blue, alpha) where
            all are 0 to 255
        """

    @abstractmethod
    def get_pixel(self, position: Position) -> Fill:
        """ Get the colour of a pixel.

        :param position: the x and y coordinates of the pixel
        :return: the colour as a tuple of (red, green, blue, alpha) where all
            are 0 to 255
        """

    @abstractmethod
    def get_size(self) -> Size:
        """ Get the size of the image.

        :return: (width, height) as a tuple
        """

    def convert_to_painter(self) -> 'LivePainter':
        return self


class LivePng(LiveImage):
    def __init__(self, png_bytes: bytes):
        """ Initialize from bytes in PNG format. """
        self.png_bytes = png_bytes

    def convert_to_png(self) -> bytes:
        """ Convert this image to bytes in PNG format.

        This version is trivial.
        """
        return self.png_bytes


class LivePillowImage(LivePainter):
    def __init__(self, image: Image.Image):
        """ Initialize from a Pillow Image.

        Use this as an example to display a live version of any other image or
        visualization class.
        """
        super().__init__()
        self.image = image

    def convert_to_png(self) -> bytes:
        data = io.BytesIO()
        self.image.save(data, 'PNG')

        return data.getvalue()

    def get_pixel(self, position: Position) -> Fill:
        return self.image.getpixel(position)

    def set_pixel(self, position: Position, fill: Fill):
        self.image.putpixel(position, fill)

    def get_size(self) -> Size:
        return self.image.size


class LiveFigure(LiveImage):
    def __init__(self, figure):
        super().__init__()
        self.figure = figure

    def convert_to_png(self) -> bytes:
        data = io.BytesIO()
        self.figure.savefig(data, format='PNG')

        return data.getvalue()


class LiveImageDiffer:
    def __init__(self, diffs_path: Path = None, request=None, is_displayed=True):
        """ Initialize the object and clean out the diffs path.

        This class requires Pillow to be installed, but you can remove that
        dependency with a subclass that overrides the start_diff() and
        end_diff() methods.
        :param diffs_path: The folder to write comparison images in, or None
            if you don't want to write any. Will be created if it doesn't exist.
        :param request: The Pytest request fixture, if you want to generate
            default file names based on the current test name.
        :param is_displayed: True if the comparison should be displayed on the
            live canvas.
        """
        self.diffs_path = diffs_path
        self.request = request
        self.is_displayed = is_displayed
        self.diff = None  # type: typing.Optional[LivePainter]
        self.diff_files = set()  # type: typing.Set[Path]
        self.tolerance = 3
        self.diff_count = 0  # number of mismatched pixels
        if self.diffs_path is not None:
            self.diffs_path.mkdir(exist_ok=True, parents=True)

    def start_diff(self, size: Size):
        self.diff = LivePillowImage(Image.new('RGBA', size))

    def end_diff(self) -> LiveImage:
        diff = self.diff
        self.diff = None
        return diff

    def compare(self,
                actual: LiveImage,
                expected: LiveImage,
                file_prefix: str = None) -> LiveImage:
        """ Build an image to highlight the differences between two images.

        Also display this image as the Actual image, the other image as the
        Expected image, and a difference between them.
        :param actual: the test image
        :param expected: the image to compare to
        :param file_prefix: base name for debug files to write when images
            aren't equal. Debug files are written when diffs_path is passed to
            __init__() and either request fixture is passed to init or
            file_prefix is passed to this method.
        """
        painter1 = actual.convert_to_painter()
        painter2 = expected.convert_to_painter()
        width, height = painter1.get_size()
        self.diff_count = 0
        self.start_diff((width, height))
        for x in range(width):
            for y in range(height):
                position = (x, y)
                fill1 = painter1.get_pixel(position)
                fill2 = painter2.get_pixel(position)
                diff_fill = self.compare_pixel(fill1, fill2)
                self.diff.set_pixel(position, diff_fill)
        self.display_diff(painter1, painter2)
        return self.end_diff()

    def assert_equal(self,
                     actual: LiveImage,
                     expected: LiveImage,
                     file_prefix: str = None):
        """ Raise an AssertionError if this image doesn't match the expected.

        Also display this image as the Actual image, the other image as the
        Expected image, and a difference between them.
        :param actual: the test image
        :param expected: the image to compare to
        :param file_prefix: base name for debug files to write when images
            aren't equal. Debug files are written when diffs_path is passed to
            __init__() and either request fixture is passed to init or
            file_prefix is passed to this method.
        """
        self.compare(actual, expected, file_prefix)
        assert self.diff_count == 0

    def compare_pixel(self, actual_pixel: Fill, expected_pixel: Fill) -> Fill:
        ar, ag, ab, aa = actual_pixel
        er, eg, eb, ea = expected_pixel
        max_diff = max(abs(a - b) for a, b in zip(actual_pixel, expected_pixel))
        if max_diff > self.tolerance:
            self.diff_count += 1
            # Colour
            dr = 0xff
            dg = (ag + eg) // 5
            db = (ab + eb) // 5

            # Opacity
            da = 0xff
        else:
            # Colour
            dr, dg, db = ar, ag, ab

            # Opacity
            da = aa // 3
        return dr, dg, db, da

    def display_diff(self, actual: LivePainter, expected: LivePainter):
        if not self.is_displayed:
            return
        if not MockTurtle.is_patched():
            return
        t = MockTurtle()
        w = t.getscreen().window_width()
        h = t.getscreen().window_height()
        ox, oy = w / 2, h / 2
        actual_width, actual_height = actual.get_size()
        expected_width, expected_height = expected.get_size()
        diff_width, diff_height = self.diff.get_size()
        text_space = (h - actual_height - diff_height - expected_height)
        text_height = max(20, text_space // 3)
        font = ('Arial', text_height // 2, 'normal')
        t.penup()
        t.goto(-ox, oy)
        t.right(90)
        t.forward(text_height)
        t.write('Actual', font=font)
        actual.display(t.pos())
        t.forward(actual_height)
        t.forward(text_height)
        t.write('Diff ({} pixels)'.format(self.diff_count), font=font)
        self.diff.display(t.pos())
        t.forward(diff_height)
        t.forward(text_height)
        t.write('Expected', font=font)
        expected.display(t.pos())


def monkey_patch_pyglet(canvas):

    pyglet = sys.modules['pyglet']

    # noinspection PyUnresolvedReferences
    class MockPygletWindow(pyglet.window.Window):

        # noinspection PyUnusedLocal
        def __init__(self, **kwargs):
            conf = pyglet.gl.Config(double_buffer=True)
            super(MockPygletWindow, self).__init__(
                config=conf,
                resizable=True,
                visible=False,

                # Let the canvas size dictate the program's window size.
                width=canvas.cget('width'),
                height=canvas.cget('height')
            )
            self.on_resize(self.width, self.height)

        @staticmethod
        def on_draw():
            # Get the colour buffer, write it to a bytearray in png format.
            buf = pyglet.image.get_buffer_manager().get_color_buffer()
            b = io.BytesIO()
            buf.save('buffer.png', b)
            LivePng(b.getvalue()).display()

    # noinspection PyUnresolvedReferences
    def run():
        for window in list(pyglet.app.windows):
            for i in range(2):
                pyglet.clock.tick()
                window.switch_to()
                window.dispatch_events()
                window.dispatch_event('on_draw')
                window.flip()
            window.close()

    # noinspection PyUnresolvedReferences
    pyglet.app.run = run
    # noinspection PyUnresolvedReferences
    pyglet.window.Window = MockPygletWindow
