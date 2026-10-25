import json,struct,unittest
from avatar_validation import audit

def glb(doc):
    raw=json.dumps(doc).encode();raw+=b' '*((-len(raw))%4)
    return b'glTF'+struct.pack('<IIII',2,20+len(raw),len(raw),0x4e4f534a)+raw

class AvatarValidationTests(unittest.TestCase):
    def fixture(self):return {'extensions':{'VRMC_vrm':{'meta':{'name':'Fixture','modification':'prohibited'},'humanoid':{'humanBones':{'hips':{'node':0}}}}},'nodes':[{'name':'Hips'}]}
    def test_prohibited_modification_and_missing_rig_not_passed(self):
        row=audit(glb(self.fixture()));self.assertFalse(row['modification_allowed']);self.assertIn('head',row['missing_required_bones']);self.assertFalse(row['visual_quality_verified'])
    def test_invalid_spring_collider_reference_reported(self):
        doc=self.fixture();doc['extensions']['VRMC_springBone']={'colliderGroups':[{'colliders':[99]}],'springs':[{'joints':[{'node':999}]}]}
        row=audit(glb(doc));self.assertIn('invalid_collider_reference',row['issues']);self.assertIn('invalid_node:spring',row['issues'])
    def test_external_resource_is_rejected_before_audit(self):
        doc=self.fixture();doc['images']=[{'uri':'https://example.com/private'}]
        with self.assertRaises(ValueError):audit(glb(doc))
    def test_vrm0_humanoid_expressions_and_physics_audit(self):
        doc={'nodes':[{'name':'Hips'},{'name':'Hair'}],'extensions':{'VRM':{
            'meta':{'title':'Leva','allowedUserName':'Everyone','licenseName':'Other'},
            'humanoid':{'humanBones':[{'bone':'hips','node':0}]},
            'blendShapeMaster':{'blendShapeGroups':[{'presetName':'blink','binds':[]},{'presetName':'a','binds':[]}]},
            'secondaryAnimation':{'boneGroups':[{'bones':[1],'colliderGroups':[]}],'colliderGroups':[]},
            'materialProperties':[{'shader':'VRM/MToon'}]}}}
        row=audit(glb(doc));self.assertEqual(row['format_version'],'0');self.assertEqual(row['human_bones']['hips'],'Hips')
        self.assertEqual(row['preset_expressions'],['a','blink']);self.assertEqual(row['spring_root_count'],1)
        self.assertEqual(row['mtoon_materials'],1);self.assertFalse(row['modification_allowed'])
        self.assertNotIn('vrm0_structural_audit_not_implemented',row['issues'])
        doc['extensions']['VRM']['secondaryAnimation']['boneGroups'][0]['colliderGroups']=[3]
        self.assertIn('invalid_collider_group',audit(glb(doc))['issues'])
