"""VIDEO_001 acceptance: fixture knowledge, isolation, refresh, links and host receipts."""
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock,patch
from second_brain import VaultIndex,SecondBrain,metadata,relative_note
from preferences import Preferences,validate_setting
from assistant_tools import AssistantTools,selected_skills
from agent_runtime import _run_agent

class SecondBrainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'Vault';self.root.mkdir()
        self.index=VaultIndex(self.root,self.base/'index')
        self.note('00_Index/START_HERE.md','# Index\n[[Proyek Leva]] dan [[Materi Diskrit]]\n')
        self.note('Projects/Proyek Leva.md','---\ntitle: Arsitektur Leva\ntags: [asisten, lokal]\naliases: [Leva]\n---\n# Leva\n## GPU\nModel ASR memakai dua GPU.\nLihat [[Materi Diskrit]].\n')
        self.note('Knowledge/Materi Diskrit.md','# Materi Diskrit\n## Jadwal\nBelajar graf hari Kamis pukul 19:00.\n[[Proyek Leva]]\n')
    def note(self,path,text):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf8');return p

    def test_list_read_and_metadata(self):
        rows=self.index.notes();self.assertEqual(len(rows),3)
        note=self.index.read('Projects/Proyek Leva.md',8,2)
        self.assertEqual(note['heading'],'GPU');self.assertIn('dua GPU',note['excerpt'])
        self.assertIn('vault=Vault',note['uri']);self.assertEqual(len(note['sha256']),64)
        parsed=metadata(self.note('m.md','').read_text(),'m.md');self.assertEqual(parsed['title'],'m')

    def test_fts_query_missing_and_injection_syntax_are_bounded(self):
        self.assertEqual(self.index.search('materi diskrit')[0]['path'],'Knowledge/Materi Diskrit.md')
        self.assertEqual(self.index.search('no_such_unique_term_88271'),[])
        self.assertEqual(self.index.search('" OR * --'),[])

    def test_wikilinks_and_backlinks_resolve_across_folders(self):
        data=self.index.related('Projects/Proyek Leva.md')
        self.assertEqual(data['links'][0]['targets'],['Knowledge/Materi Diskrit.md'])
        self.assertIn('Knowledge/Materi Diskrit.md',data['backlinks'])
        self.assertIn('00_Index/START_HERE.md',data['backlinks'])

    def test_ambiguous_links_and_alias_are_not_silently_guessed(self):
        self.note('Other/Materi Diskrit.md','# Duplicate\n')
        data=self.index.related('00_Index/START_HERE.md');self.assertIn('Materi Diskrit',data['ambiguous_links'])
        self.assertEqual(VaultIndex.targets('Leva#GPU|alias','00_Index/START_HERE.md',{'Projects/Proyek Leva.md':{'aliases':['Leva']}}),['Projects/Proyek Leva.md'])

    def test_change_delete_and_cache_refresh(self):
        self.index.refresh();self.assertEqual(self.index.refresh()['updated'],0)
        self.note('Knowledge/Materi Diskrit.md','# Matematika\nKombinatorika terbaru\n')
        self.assertEqual(self.index.search('kombinatorika')[0]['path'],'Knowledge/Materi Diskrit.md')
        (self.root/'Knowledge/Materi Diskrit.md').unlink()
        self.assertEqual(self.index.search('kombinatorika'),[])

    def test_direct_and_index_reads_deny_dotfiles_secrets_and_traversal(self):
        self.note('.obsidian/config.md','SECRET');self.note('api-key.md','SECRET');self.note('private/.hidden.md','SECRET')
        for path in ('../outside.md','/outside.md','C:/outside.md','.obsidian/config.md','api-key.md','private/.hidden.md'):
            with self.subTest(path=path),self.assertRaises(ValueError):self.index.read(path)
        self.assertEqual(len(self.index.notes()),3)

    def test_symlink_or_junction_escape_denied(self):
        outside=self.base/'Outside';outside.mkdir();(outside/'outside.md').write_text('SECRET')
        link=self.root/'escape'
        try:
            try:link.symlink_to(outside,target_is_directory=True)
            except OSError:
                import _winapi
                _winapi.CreateJunction(str(outside),str(link))
        except (OSError,ImportError):self.skipTest('OS cannot create fixture link')
        with self.assertRaises(ValueError):self.index.read('escape/outside.md')
        self.assertFalse(any('outside' in row['path'] for row in self.index.notes()))

    def test_ignore_rules_apply_to_search_and_explicit_read(self):
        self.note('Drafts/draft.md','# Not indexed\n')
        self.note('scratch.md','# Scratch\n');self.note('keep.md','# Keep\n')
        (self.root/'.gitignore').write_text('Drafts/\n*.md\n!keep.md\n!00_Index/\n!Projects/\n!Knowledge/\n')
        self.assertEqual([r['path'] for r in self.index.notes()],['keep.md'])
        with self.assertRaises(ValueError):self.index.read('scratch.md')
        with self.assertRaises(ValueError):self.index.read('Drafts/draft.md')

    def test_internal_link_cannot_alias_hidden_configuration(self):
        hidden=self.root/'.obsidian';hidden.mkdir();(hidden/'config.md').write_text('SECRET')
        link=self.root/'alias'
        try:
            try:link.symlink_to(hidden,target_is_directory=True)
            except OSError:
                import _winapi
                _winapi.CreateJunction(str(hidden),str(link))
        except (OSError,ImportError):self.skipTest('OS cannot create fixture link')
        with self.assertRaises(ValueError):self.index.read('alias/config.md')
        self.assertEqual(len(self.index.notes()),3)

    def test_large_metadata_and_list_output_are_bounded(self):
        for i in range(6):self.note(str(i)+'.md','---\ntitle: '+('a'*4000)+'\ntags: ['+(','.join('tag'+str(n)+'x'*80 for n in range(40)))+']\n---\n# '+('h'*4000)+'\n')
        rows=self.index.notes();self.assertLessEqual(sum(len(json.dumps(r,ensure_ascii=False)) for r in rows),6000)
        parsed=metadata('---\ntitle: '+('a'*4000)+'\n---\n','x.md');self.assertEqual(len(parsed['title']),200)

    def test_nested_ignore_and_local_exclusions(self):
        self.note('Projects/private.md','hidden')
        (self.root/'Projects/.levaignore').write_text('private.md\n')
        self.assertEqual(self.index.search('hidden'),[])
        with self.assertRaises(ValueError):self.index.read('Projects/private.md')

    def test_empty_malformed_markdown_and_invalid_utf8(self):
        self.note('empty.md','');self.note('odd.md','---\nnot yaml\n[[unclosed\n# Valid heading\n')
        p=self.note('bad.md','good');self.index.refresh();p.write_bytes(b'\xff\xfeinvalid')
        stats=self.index.refresh(force=True);self.assertGreater(stats['errors'],0)
        self.assertNotIn('bad.md',[r['path'] for r in self.index.notes()])
        self.assertEqual(self.index.read('empty.md')['excerpt'],'')
        self.assertEqual(self.index.read('odd.md')['heading'],'Valid heading')

    def test_large_notes_and_non_markdown_rejected(self):
        self.note('large.md','x'*128001)
        with self.assertRaises(ValueError):self.index.read('large.md')
        with self.assertRaises(ValueError):self.index.read('file.exe')
        self.assertNotIn('large.md',[r['path'] for r in self.index.notes()])

    def test_permission_error_invalidates_old_cached_content(self):
        self.index.refresh()
        original=VaultIndex.read_bytes
        def blocked(path):
            if path.name=='Materi Diskrit.md':raise PermissionError('fixture')
            return original(path)
        with patch.object(VaultIndex,'read_bytes',side_effect=blocked):
            stats=self.index.refresh(force=True);self.assertGreater(stats['errors'],0)
            with self.index.connection() as db:self.assertIsNone(db.execute('SELECT path FROM notes WHERE path=?',('Knowledge/Materi Diskrit.md',)).fetchone())

    def test_notes_are_redacted_and_audit_contains_no_body_query_or_root(self):
        self.note('test.md','# private marker_body_1891\npassword: hidden_123\n')
        result=self.index.search('marker_body_1891');self.assertNotIn('hidden_123',json.dumps(result))
        audit=(self.base/'index/audit.jsonl').read_text()
        self.assertNotIn('marker_body_1891',audit);self.assertNotIn(str(self.root),audit);self.assertNotIn('hidden_123',audit)

    def test_readonly_service_and_configuration(self):
        prefs=Preferences(self.base/'prefs.db');self.addCleanup(prefs.close)
        service=SecondBrain(prefs,self.base/'service')
        self.assertEqual(service.run({'action':'search','query':'x'})['status'],'needs_input')
        prefs.set('obsidian_vault',str(self.root));self.assertTrue(service.status()['configured'])
        before={p:p.read_bytes() for p in self.root.rglob('*.md')}
        self.assertEqual(service.run({'action':'write','path':'test.md'})['code'],'second_brain_read_only')
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*.md')})
        self.assertEqual(service.run({'action':'read','path':'Projects/Proyek Leva.md'})['status'],'done')
        with self.assertRaises(ValueError):validate_setting('obsidian_vault','relative')

    def test_cancellation_and_search_excerpt_budget(self):
        with self.assertRaisesRegex(ValueError,'cancelled'):self.index.refresh(authorized=lambda:False)
        for i in range(8):self.note(str(i)+'.md','# Benchmark\n'+('common '*900+'\n')*2)
        result=self.index.search('common',8);self.assertLessEqual(sum(len(r['excerpt']) for r in result),6000)

    def test_host_registry_and_agent_citations_from_real_read(self):
        self.assertIn('obsidian_action',{s.name for s in selected_skills('Baca catatan Obsidian saya')})
        prefs=Preferences(self.base/'prefs.db');self.addCleanup(prefs.close);prefs.set('obsidian_vault',str(self.root))
        tools=AssistantTools.__new__(AssistantTools);tools.desktop=Mock(preferences=prefs);tools._resume_goal='';tools._continuation=None
        tools._second_brain=SecondBrain(prefs,self.base/'service')
        local=Mock();local.propose_tool.side_effect=[{'action':'obsidian_action','args':{'action':'read','path':'Knowledge/Materi Diskrit.md'}},
            {'action':'respond','args':{'text':'Menurut catatan, belajar graf Kamis pukul 19:00.','speech_text':'Belajar graf Kamis pukul 19:00.'}}]
        commands=queue.Queue()
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':tools.execute(event['name'],event['args'],'Baca catatan Obsidian saya')})
        result=_run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Baca catatan Obsidian saya'}]},local,commands,emit)
        self.assertIn('Knowledge/Materi Diskrit.md',result['response']);self.assertNotIn('.md',result['speech_text'])

if __name__=='__main__':unittest.main()
