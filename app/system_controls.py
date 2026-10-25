"""On-demand volume and brightness controls, verified by reading the setting again."""


def control(args):
    action=args['action'];value=args.get('value','')
    if action in ('volume','mute','audio_status'):
        from pycaw.pycaw import AudioUtilities
        device=AudioUtilities.GetSpeakers();endpoint=device.EndpointVolume
        before={'volume_percent':round(endpoint.GetMasterVolumeLevelScalar()*100),'muted':bool(endpoint.GetMute())}
        if action=='volume':
            wanted=int(value)
            if not 0<=wanted<=100:raise ValueError('volume_range_0_100')
            endpoint.SetMasterVolumeLevelScalar(wanted/100,None)
        elif action=='mute':
            if value not in ('on','off'):raise ValueError('mute_requires_on_off')
            endpoint.SetMute(1 if value=='on' else 0,None)
        after={'volume_percent':round(endpoint.GetMasterVolumeLevelScalar()*100),'muted':bool(endpoint.GetMute())}
        verified=action=='audio_status' or action=='volume' and abs(after['volume_percent']-wanted)<=1 or action=='mute' and after['muted']==(value=='on')
        return {'status':'done' if verified else 'unverified','reply':'Pengaturan audio dibaca kembali.','device':device.FriendlyName,'before':before,'after':after,'task_verified':verified}
    if action in ('brightness','display_status'):
        import screen_brightness_control as sbc
        index=int(args.get('display','0'));before=sbc.get_brightness(display=index)
        if action=='brightness':
            wanted=int(value)
            if not 1<=wanted<=100:raise ValueError('brightness_range_1_100')
            sbc.set_brightness(wanted,display=index)
        after=sbc.get_brightness(display=index)
        verified=action=='display_status' or bool(after) and all(abs(v-wanted)<=2 for v in after)
        return {'status':'done' if verified else 'unverified','reply':'Kecerahan layar dibaca kembali.','display':index,'before':before,'after':after,'task_verified':verified}
    raise ValueError('unsupported_system_setting')
