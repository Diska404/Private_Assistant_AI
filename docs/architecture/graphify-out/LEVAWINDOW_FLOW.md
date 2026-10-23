# Penelusuran LevaWindow - 23 Oktober 2026

Expanded from original query via graph vocabulary: [leva, rooms, chat, secret, voice, web, bridge, agent, journal, route, reply, microphone].

Graph: 2356 nodes, 7381 undirected links. BFS found 939 nodes; its 2400-token view was truncated, so key nodes and edges were inspected separately and checked against production source. This is static analysis, not a live acceptance test.

## Findings

LevaWindow is the UI coordinator. It initializes desktop/chat services at gui.py:L35, ConversationRooms at L39 and ReplyVoice at L48. Graph class-use edges are marked INFERRED 0.95; source inspection confirms these constructions.

Typed desktop input and queued microphone commands converge on LevaWindow.send (gui.py:L214; dispatch_voice calls it at L1140). Mobile/web commands are dequeued by DesktopWebHost.poll and forwarded to main.send with client context, workspace and attachments (web_host.py:L133-L145). DesktopWebHost is constructed by LevaWindow.open_web at gui.py:L730; it creates WebBridge at web_host.py:L20. These edges and source locations establish shared dispatch, not independent agents on the phone.

send chooses Chat/Secret via send_room at gui.py:L233-L236; Assistant can also enter this conversation-only path if a model in NO_AGENT is selected. send_room calls ConversationRooms.answer (room_ui.py:L93). ConversationRooms keeps per-room SQLite logs and restores service history (conversation_rooms.py:L41-L60). Chat auto selects qwen4b for personal intent or saluki otherwise (L91-L99), with optional read-only public research (L101-L104). The worker rejects tool contexts/executors and nonlocal routes for room purposes (chat_service.py:L71,L189). Secret proposes handoff at room_ui.py:L89-L92; accepted handoff copies stored rows and dispatches the original goal at L164-L183. Active model context is bounded, even though stored rows are copied.

Assistant first uses DesktopService.handle (gui.py:L304). Remaining requests can pass through conversation_request (L325): explicit action words bypass the extra frontend inference; normal frontend inference uses minicpm2b (conversation_frontend.py:L47-L61). Delegated requests go to ChatService.ask with a host tool executor at gui.py:L342-L345. The worker calls run_agent at chat_service.py:L139-L140. run_agent wraps _run_agent with TaskJournal recording intent/receipt/plan and continuation state (agent_runtime.py:L64-L100). LevaWindow.execute_tool passes calls to desktop.tools.execute (gui.py:L995-L997). This is the agent execution branch, distinct from room-only chat.

Results return through LevaWindow.poll (gui.py:L420), which handles generation IDs, progress, errors and completion (L435-L508). Japanese speech can be produced after Indonesian text has already been published (room_ui.py:L97-L107). speak_reply selects voice pack/output/GPU and forwards to ReplyVoice (gui.py:L929-L971). ReplyVoice chunks speech and sends it to VoicePackService (reply_voice.py:L76-L100). DesktopWebHost.bind_audio publishes generated audio through the bridge (web_host.py:L35-L39).

Web state is published on a 0.25-second throttle, with phase, workspace, models, mic levels, GPU/RAM snapshot and voice progress (web_host.py:L149-L169); freshness depends on upstream measurements. Active Android/iOS presence pauses laptop microphone handling (L105-L114), and the web state declares push_to_talk_draft (L168).

## Interpretation and limits

The shared UI dispatch provides a consistent execution path across desktop and phone. Workspace selection and model selection are separate from ASR/TTS GPU selection. Agent capability comes from the executable tools and verification loop; choosing a larger model alone does not add tools.

The graph is undirected. A shortest path through main.py or a test file is not an execution sequence. EXTRACTED links denote static calls/imports, while INFERRED links need verification. Source-confirmed connections above are distinguished from graph-only inference; the graph itself has not been silently relabeled.

Potential constraints: LevaWindow.send and send_room cap user text at 3000 characters; room content/context is bounded; Secret routing and Chat auto-routing combine rules and a model classifier and are not proven perfectly accurate; shared-GPU ASR/agent/TTS work can run sequentially due to VRAM limits. No responsiveness, audio naturalness, or full PC-control claim was tested in this trace.
