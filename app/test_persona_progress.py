import random
import unittest
from leva_persona import PersonaDelivery,ACKS
from task_progress import TaskProgress
from development_diagnostics import diagnose

class PersonaProgressTests(unittest.TestCase):
    def test_no_default_address_and_no_adjacent_repetition(self):
        delivery=PersonaDelivery(random.Random(42));rows=[delivery.greeting(playful=False)['text'] for _ in range(32)]
        for start in range(0,32,4):
            self.assertTrue(all(any(name in line for line in rows[start:start+4]) for name in ('Raizei','Shikikan','Sensei','my Shikikan')))
        self.assertTrue(all(a!=b for a,b in zip(rows,rows[1:])))
    def test_acknowledgements_cycle_without_repeating_adjacent(self):
        d=PersonaDelivery(random.Random(7));rows=[d.acknowledgement('buka aplikasi') for _ in range(24)]
        self.assertEqual(set(rows),set(ACKS['work']))
        self.assertTrue(all(a!=b for a,b in zip(rows,rows[1:])))
    def test_tool_events_do_not_expose_command_or_invent_success(self):
        p=TaskProgress();p.begin('Asisten');p.tool('terminal',{'action':'start','code':'PRIVATE_API_KEY'});p.tool('terminal',{'action':'start'},{'status':'failed'})
        rows=p.snapshot();self.assertEqual(rows[-1]['status'],'failed');self.assertNotIn('PRIVATE_API_KEY',str(rows))
        p.tool('computer_action',{'action':'click'},{'status':'dispatched'})
        self.assertIn('perlu verifikasi',p.snapshot()[-1]['label'])
    def test_successful_exit_is_not_a_failure_from_printed_error_word(self):
        self.assertEqual(diagnose('example error: this is documentation',0),{})
        self.assertEqual(diagnose('ImportError: cannot import name x',1)['category'],'import_error')
        result=diagnose('File "C:/project/main.py", line 13\nSyntaxError: invalid syntax',1)
        self.assertEqual(result['traceback'][0]['line'],13)
        self.assertTrue(result['untrusted_data'])

if __name__=='__main__':unittest.main()
