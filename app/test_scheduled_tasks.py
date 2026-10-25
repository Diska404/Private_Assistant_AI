from datetime import datetime,timedelta
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock,patch
from command_resolution import WIB
from scheduled_tasks import ScheduleStore,parse_schedule,deferred_request,completion_status
from desktop_service import DesktopService
from assistant_tools import AssistantTools,requested_urls
from agent_runtime import run_agent
from gui import LevaWindow

REQUEST='leva, buatkan jadwal memo untuk malam ini agar saya mengerjakan tugas matematika diskrit yaitu jam 19:00, habis itu langung buka chrome saya yang diska untuk langsung membuka chatgpt dan buka edge untuk ke web edlink'
INVENTORY={'profiles':[{'id':'chrome-stable:Profile 1','name':'Diska','channel':'stable','profile_directory':'Profile 1','user_data_root':'C:/fixture','directory_exists':True}]}


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'jobs.sqlite3';self.store=ScheduleStore(self.path)
        self.now=datetime(2026,10,20,18,0,tzinfo=WIB)
        with patch('desktop_service.inspect_profiles',return_value=INVENTORY):
            self.desktop=DesktopService(Mock(),schedules=self.store)

    def test_reported_request_is_saved_without_launching_any_browser(self):
        result=self.desktop.handle(REQUEST,self.now)
        self.assertEqual(result['status'],'done');self.desktop.browser.launch.assert_not_called()
        row=self.store.recent()[0]
        self.assertEqual(row['when'],'2026-10-20T19:00:00+07:00')
        self.assertIn('matematika diskrit',row['title']);self.assertIn('chrome',row['goal']);self.assertIn('edge',row['goal']);self.assertIn('edlink',row['goal'])
        self.assertIsNone(self.store.claim(self.now));self.assertEqual(self.store.notifications(self.now),[])

    def test_elapsed_today_is_not_silently_tomorrow_or_opened_now(self):
        result=self.desktop.handle(REQUEST,self.now+timedelta(hours=2))
        self.assertEqual(result['status'],'needs_input');self.assertIn('sudah lewat',result['reply'])
        self.assertEqual(self.store.recent(),[]);self.desktop.browser.launch.assert_not_called()

    def test_explicit_date_tomorrow_and_relative_times(self):
        for text,expected in [('ingatkan belajar besok jam 19:00','2026-10-21T19:00:00+07:00'),('ingatkan belajar tanggal 2026-10-25 jam 19.30','2026-10-25T19:30:00+07:00'),('ingatkan belajar dalam 2 menit','2026-10-20T18:02:00+07:00')]:
            self.assertEqual(parse_schedule(text,self.now)['when'],expected)

    def test_reported_spoken_relative_time_and_text_retry_keep_deferred_scope(self):
        for phrase in ('Nanti 2 menit lagi','Dua menit lagi','Dalam dua menit'):
            text=phrase+' ingatkan saya belajar matematika diskrit, lalu buka Chrome Diska dan Edge. Jangan buka browser sebelum waktunya.'
            result=self.desktop.handle(text,self.now)
            self.assertEqual(result['status'],'done')
            self.assertEqual(result['schedule']['when'],'2026-10-20T18:02:00+07:00')
            self.assertIn('Chrome Diska',result['schedule']['goal']);self.assertIn('Edge',result['schedule']['goal'])
            self.assertNotIn('Jangan',result['schedule']['goal'])
        self.desktop.browser.launch.assert_not_called()
        for text in ('jangan ingatkan saya dalam 2 menit','contoh ingatkan dalam dua menit','ingatkan saya 2 menit lagi atau 3 menit lagi'):
            if deferred_request(text):
                with self.assertRaises(ValueError):parse_schedule(text,self.now)

    def test_ambiguous_multiple_invalid_and_recurring_times_do_not_execute(self):
        for text in ('ingatkan belajar nanti','ingatkan belajar jam 25:00','ingatkan belajar jam 19:00 atau jam 20:00','ingatkan belajar hari jumat jam 19:00','ingatkan setiap hari jam 19:00'):
            with self.subTest(text=text):self.assertEqual(self.desktop.handle(text,self.now)['status'],'needs_input')
        self.assertEqual(self.store.recent(),[])

    def test_task_time_prefix_is_also_deferred(self):
        result=self.desktop.handle('jam 19:00 buka Chrome Diska untuk ChatGPT',self.now)
        self.assertEqual(result['schedule']['goal'],'buka Chrome Diska untuk ChatGPT')
        self.desktop.browser.launch.assert_not_called()
        result=self.desktop.handle('buka Chrome Diska untuk ChatGPT jam 19:00',self.now)
        self.assertEqual(result['status'],'done');self.desktop.browser.launch.assert_not_called()

    def test_cancel_list_and_persistence(self):
        row=self.store.add(**parse_schedule(REQUEST,self.now),now=self.now)
        reopened=ScheduleStore(self.path);self.assertEqual(reopened.recent()[0]['id'],row['id'])
        self.assertIn(row['id'],self.desktop.handle('lihat daftar pengingat',self.now)['reply'])
        self.assertEqual(self.desktop.handle('batalkan pengingat '+row['id'],self.now)['status'],'done')
        self.assertIsNone(reopened.claim(self.now+timedelta(hours=1)));self.assertEqual(reopened.notifications(self.now+timedelta(hours=1)),[])

    def test_due_notification_and_claim_are_once_across_reopen(self):
        self.store.add(**parse_schedule(REQUEST,self.now),now=self.now);due=self.now+timedelta(hours=1)
        self.assertEqual(len(self.store.notifications(due)),1);self.assertEqual(ScheduleStore(self.path).notifications(due),[])
        self.assertEqual(self.store.claim(due)['status'],'running');self.assertIsNone(ScheduleStore(self.path).claim(due))

    def test_stale_actions_and_crashed_tasks_are_not_replayed(self):
        self.store.add(**parse_schedule(REQUEST,self.now),now=self.now)
        self.assertEqual(self.store.claim(self.now+timedelta(hours=2))['status'],'needs_input')
        self.assertIsNone(self.store.claim(self.now+timedelta(hours=2)))
        row=self.store.add('second',(self.now+timedelta(minutes=1)).isoformat(),'buka Notepad',self.now)
        self.store.claim(self.now+timedelta(minutes=1));self.assertEqual(ScheduleStore(self.path).recover(),1)
        self.assertIsNone(self.store.claim(self.now+timedelta(minutes=2)))

    def window(self):
        window=LevaWindow.__new__(LevaWindow);window.desktop=self.desktop;window.busy=False
        window.entry=Mock();window.entry.get.return_value='';window.reply_voice=Mock(active=False)
        window.notify_schedule=Mock();window.send=Mock();window.add=Mock();window._scheduled_job=None
        return window

    def test_timer_waits_for_draft_and_pause_then_dispatches_literal_goal(self):
        self.store.add(**parse_schedule(REQUEST,self.now),now=self.now);due=self.now+timedelta(hours=1)
        window=self.window();self.desktop.paused=True;window.poll_schedules(due)
        window.notify_schedule.assert_not_called();window.send.assert_not_called()
        self.desktop.paused=False;window.entry.get.return_value='unsent private draft';window.poll_schedules(due)
        window.notify_schedule.assert_called_once();window.send.assert_not_called();window.entry.delete.assert_not_called()
        window.entry.get.return_value='';window.poll_schedules(due)
        window.send.assert_called_once();self.assertIn('edlink',window.send.call_args.args[0]);self.assertIn('scheduled_id',window.send.call_args.kwargs)

    def test_reminder_without_action_completes_and_interruption_is_durable(self):
        self.store.add('belajar',(self.now+timedelta(minutes=1)).isoformat(),now=self.now)
        window=self.window();window.poll_schedules(self.now+timedelta(minutes=1));window.send.assert_not_called()
        self.assertEqual(self.store.recent()[0]['status'],'completed')
        row=self.store.add('task',(self.now+timedelta(minutes=2)).isoformat(),'buka Notepad',self.now)
        self.store.claim(self.now+timedelta(minutes=2));window._scheduled_job=row['id'];window.interrupt_schedule()
        self.assertEqual(next(r for r in self.store.recent() if r['id']==row['id'])['status'],'interrupted')

    def test_multi_goal_bypasses_single_chrome_shortcut(self):
        self.assertEqual(self.desktop.handle('buka Chrome Diska untuk ChatGPT dan buka Edge untuk EdLink',self.now)['kind'],'chat')
        self.desktop.browser.launch.assert_not_called()

    def test_host_rejects_immediate_open_from_deferred_user_request(self):
        tools=AssistantTools.__new__(AssistantTools);tools.desktop=self.desktop
        result=tools.execute('open_browser',{'profile':'Diska','url':'https://chatgpt.com/'},REQUEST)
        self.assertEqual(result['status'],'needs_input');self.desktop.browser.launch.assert_not_called()

    def test_edge_and_second_url_are_preserved(self):
        text='buka Chrome Diska untuk ChatGPT dan buka Edge untuk EdLink'
        self.assertEqual(requested_urls(text),{'https://chatgpt.com/','https://edlink.id/'})
        tools=AssistantTools.__new__(AssistantTools);tools.desktop=self.desktop;tools.allowed_web_urls=set()
        with patch.object(self.desktop,'open_edge',return_value={'status':'done','reply':'Edge window observed'}) as edge:
            result=tools.execute('open_browser',{'profile':'','url':'https://edlink.id/','browser':'edge'},text)
        self.assertEqual(result['status'],'done');edge.assert_called_once()

    def test_direct_edlink_request_goes_to_edge(self):
        with patch.object(self.desktop,'open_edge',return_value={'status':'done','reply':'Observed'}) as edge:
            result=self.desktop.handle('buka Edge untuk EdLink',self.now)
        edge.assert_called_once_with('https://edlink.id/');self.assertEqual(result['status'],'done')

    def test_edge_launcher_keeps_url_literal_without_shell(self):
        with patch('desktop_service.Path.is_file',return_value=True),patch('windows_runtime.application_windows',side_effect=[[],[123]]),patch('desktop_service.subprocess.Popen') as launch:
            result=self.desktop.open_edge('https://edlink.id/')
        args=launch.call_args.args[0]
        self.assertEqual(args[1:],['--new-window','https://edlink.id/']);self.assertNotIn('shell',launch.call_args.kwargs)
        self.assertEqual(result['status'],'done');self.assertFalse(result['evidence']['page_verified'])

    def test_agent_cannot_finish_after_only_first_browser(self):
        local=Mock();local.propose_tool.side_effect=[
            {'action':'open_browser','args':{'profile':'Diska','url':'https://chatgpt.com/'}},
            {'action':'respond','args':{'text':'Selesai','speech_text':'Selesai'}},
            {'action':'open_browser','args':{'profile':'','url':'https://edlink.id/','browser':'edge'}},
            {'action':'respond','args':{'text':'Kedua permintaan terkirim.','speech_text':'Kedua permintaan terkirim.'}}]
        commands=queue.Queue();events=[]
        def emit(event):
            events.append(event);commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','reply':'Jendela terdeteksi.'}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'buka Chrome Diska untuk ChatGPT dan buka Edge untuk EdLink'}]},local,commands,emit)
        self.assertEqual(len(events),2);self.assertEqual(len(result['tool_receipts']),2)

    def test_completion_requires_evidence_and_keeps_failure(self):
        self.assertEqual(completion_status({'response':'Sudah kubuka'}),'incomplete')
        self.assertEqual(completion_status({'status':'done'}),'completed')
        self.assertEqual(completion_status({'tool_receipts':[{'result':{'status':'unverified'}}]}),'incomplete')
        self.assertEqual(completion_status({'error':'failure'}),'failed')


if __name__=='__main__':unittest.main()
