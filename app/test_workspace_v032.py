import io,json,tempfile,unittest,zipfile
from pathlib import Path
from PIL import Image
from profile_avatar import ProfileAvatar
from conversation_attachments import extract_upload,materialize,ConversationUploads,compose_message

class WorkspaceTests(unittest.TestCase):
    def archive(self,files):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for name,value in files.items():z.writestr(name,value)
        return out.getvalue()
    def test_avatar_crop_position_zoom_and_failed_confirmation_preserve_existing(self):
        image=Image.new('RGB',(800,400),'red');image.paste('blue',(400,0,800,400));raw=io.BytesIO();image.save(raw,format='PNG')
        with tempfile.TemporaryDirectory() as folder:
            avatar=ProfileAvatar(folder);avatar.save(raw.getvalue(),{'x':1,'y':.5,'zoom':1})
            result=Image.open(io.BytesIO(avatar.read()));self.assertEqual(result.getpixel((256,256))[:3],(0,0,255));before=avatar.read()
            for framing in ({'x':float('nan'),'y':0,'zoom':1},{'x':0,'y':0,'zoom':0},{'x':0,'y':0}):
                with self.assertRaises(ValueError):avatar.save(raw.getvalue(),framing)
                self.assertEqual(avatar.read(),before)
            avatar.save(raw.getvalue(),{'x':0,'y':.5,'zoom':2});self.assertEqual(Image.open(io.BytesIO(avatar.read())).getpixel((256,256))[:3],(255,0,0))
    def test_office_and_archive_decoders_report_what_was_read(self):
        doc=self.archive({'word/document.xml':'<document><p><t>Matematika Diskrit</t></p></document>'})
        self.assertIn('Matematika Diskrit',extract_upload('materi.docx',doc)['text'])
        deck=self.archive({'ppt/slides/slide1.xml':'<slide><t>Teori Graf</t></slide>'})
        self.assertIn('Teori Graf',extract_upload('presentasi.pptx',deck)['text'])
        sheet=self.archive({'xl/sharedStrings.xml':'<sst><si><t>Nama</t></si></sst>','xl/worksheets/sheet1.xml':'<worksheet><c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c></worksheet>'})
        self.assertIn('A1: Nama',extract_upload('nilai.xlsx',sheet)['text']);self.assertIn('B1: 42',extract_upload('nilai.xlsx',sheet)['text'])
        archive=extract_upload('data.zip',doc);self.assertEqual(archive['kind'],'archive_inventory');self.assertIn('belum',archive['limitation'])
    def test_opaque_binary_and_image_metadata_never_claim_content_understanding(self):
        row=extract_upload('data.bin',b'\x00\x01\x02\xff');self.assertEqual(row['kind'],'unsupported_binary');self.assertIn('belum dibaca',row['limitation'])
        raw=io.BytesIO();Image.new('RGB',(20,30)).save(raw,format='PNG');image=extract_upload('scene.png',raw.getvalue());self.assertEqual(image['kind'],'image_metadata');self.assertIn('belum dianalisis',image['limitation'])
        self.assertIn('belum dianalisis',compose_message('Apa isinya?',[image]))
    def test_xml_entities_are_rejected_and_legacy_text_encoding_is_supported(self):
        bad=self.archive({'word/document.xml':'<!DOCTYPE x [<!ENTITY a "x">]><doc>&a;</doc>'})
        with self.assertRaises(ValueError):extract_upload('bad.docx',bad)
        self.assertEqual(extract_upload('catatan.txt','Halo Leva'.encode('utf16'))['text'],'Halo Leva')
        self.assertIn('satu',extract_upload('catatan.toml',b'name="satu"')['text'])

    def test_agent_file_read_uses_office_parser_without_launching_office(self):
        from file_workspace import FileWorkspace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'materi.docx';path.write_bytes(self.archive({'word/document.xml':'<doc><p>Teori Graf</p></doc>'}))
            files=FileWorkspace(root/'history');files.observed.add(str(path))
            result=files.run({'action':'read','path':str(path)},'baca materi',lambda:True)
            self.assertIn('Teori Graf',result['content']);self.assertEqual(result['kind'],'document_text')
    def test_local_reference_reads_at_send_and_does_not_paste_into_composer(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'note.md';path.write_text('old');rows=[{'name':path.name,'local_reference':str(path),'truncated':False}];path.write_text('current')
            result=materialize(rows);self.assertEqual(result[0]['text'],'current');self.assertNotIn('text',rows[0])
    def test_upload_is_still_session_bound_with_new_formats(self):
        store=ConversationUploads();row=store.save('phone-a','note.ini',b'[User]\nname=Raizei')
        self.assertNotIn('text',row)
        with self.assertRaises(ValueError):store.resolve('phone-b',[row['id']])
        self.assertIn('Raizei',store.resolve('phone-a',[row['id']])[0]['text'])

    def test_avatar_http_crop_and_assistant_attachment_are_authenticated(self):
        import urllib.request,urllib.error
        from unittest.mock import Mock
        from web_bridge import WebBridge
        with tempfile.TemporaryDirectory() as folder:
            bridge=WebBridge(Mock(),port=0,avatar=ProfileAvatar(folder));bridge.update({'workspace':'assistant'});bridge.start()
            try:
                image=Image.new('RGB',(800,400),'red');image.paste('blue',(400,0,800,400));raw=io.BytesIO();image.save(raw,format='PNG')
                headers={'Origin':bridge.origin,'Cookie':'leva_session='+bridge.cookie,'X-Leva-Crop':json.dumps({'x':1,'y':.5,'zoom':1})}
                request=urllib.request.Request(bridge.origin+'/api/avatar',data=raw.getvalue(),method='POST',headers=headers)
                with urllib.request.urlopen(request,timeout=3) as response:self.assertEqual(response.status,200)
                self.assertEqual(Image.open(io.BytesIO(bridge.avatar.read())).getpixel((256,256))[:3],(0,0,255))
                row=bridge.uploads.save('desktop','note.toml',b'name="Leva"')
                result=bridge.submit({'id':'assistant-attachment-fixture','kind':'chat','value':{'workspace':'assistant','text':'Baca lampiran','attachments':[row['id']]}})
                self.assertEqual(result['status'],'queued')
                for path in ('/workspace.js','/workspace.css'):
                    with urllib.request.urlopen(bridge.origin+path,timeout=3) as response:self.assertEqual(response.status,200)
            finally:bridge.stop();bridge.store.db.close()

if __name__=='__main__':unittest.main()
