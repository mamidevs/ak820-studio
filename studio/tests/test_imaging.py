import io
import unittest
from PIL import Image, ImageDraw
from ak820.imaging import inspect_image, normalize_settings, quantize565, render, text_fit
from ak820.protocol import rgb565

class ImagingTests(unittest.TestCase):
    def encode(self, im, kind='PNG', **kw):
        out=io.BytesIO(); im.save(out,format=kind,**kw); return out.getvalue()

    def test_preview_quantization_preserves_payload(self):
        im=Image.new('RGB',(128,128)); im.putdata([(i%256,(i*17)%256,(i*83)%256) for i in range(128*128)])
        self.assertEqual(rgb565(im),rgb565(quantize565(im)))

    def test_contain_background_crop_and_pan(self):
        im=Image.new('RGB',(256,128),'red')
        for x in range(128,256):
            for y in range(128): im.putpixel((x,y),(0,0,255))
        data=self.encode(im)
        frames,_,_=render(data,{'fit':'contain','background':'#00ff00'})
        self.assertEqual(frames[0].getpixel((64,0)),(0,255,0))
        left,_,_=render(data,{'x':-1}); right,_,_=render(data,{'x':1})
        self.assertEqual(left[0].getpixel((64,64)),(255,0,0))
        self.assertEqual(right[0].getpixel((64,64)),(0,0,255))

    def test_gif_frames_and_delay_normalization(self):
        a=Image.new('RGB',(16,16),'red'); b=Image.new('RGB',(16,16),'blue')
        data=self.encode(a,'GIF',save_all=True,append_images=[b],duration=[100,1000],loop=0)
        frames,delays,warnings=render(data,{})
        self.assertEqual(inspect_image(data)['frame_count'],2)
        self.assertEqual(delays,[100,510]); self.assertTrue(warnings)
        self.assertNotEqual(frames[0].tobytes(),frames[1].tobytes())

    def test_reject_invalid_input_and_nan(self):
        with self.assertRaises(ValueError): inspect_image(b'not an image')
        with self.assertRaises(ValueError): normalize_settings({'zoom':float('nan')})
        with self.assertRaises(ValueError): normalize_settings({'effect':'arbitrary'})

    def test_over_frame_limit_rejected(self):
        images=[Image.new('RGB',(2,2),(i,0,0)) for i in range(141)]
        data=self.encode(images[0],'GIF',save_all=True,append_images=images[1:],duration=50)
        with self.assertRaisesRegex(ValueError,'140'): inspect_image(data)

    def test_long_template_text_is_ellipsized_to_measured_slot_width(self):
        draw=ImageDraw.Draw(Image.new('RGB',(128,128)))
        for max_size,width in [(15,93),(8,93),(22,112),(9,112)]:
            with self.subTest(max_size=max_size,width=width):
                label,used_font=text_fit(draw,'W'*40,max_size,width)
                self.assertTrue(label.endswith('…'))
                self.assertLess(len(label),40)
                self.assertGreaterEqual(used_font.size,7)
                self.assertLessEqual(draw.textlength(label,font=used_font),width)
        label,used_font=text_fit(draw,'AK820',15,93)
        self.assertEqual(label,'AK820')
        self.assertEqual(used_font.size,15)
        label,used_font=text_fit(draw,'ÜST\nALT',15,93)
        self.assertEqual(label,'ÜST ALT')
        self.assertLessEqual(draw.textlength(label,font=used_font),93)

if __name__=='__main__': unittest.main()
