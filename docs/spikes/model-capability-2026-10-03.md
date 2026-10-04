# Model capability spike — 2026-10-03

A9 project `ttrpg` (served model: `ttrpg/local-coder`), mode `json_object`, N=50 per case.
Budgets for comparison: `docs/specifications/turn-budget-and-latency.md` §3.

| case | role | valid raw | valid after 1 repair | key pass | authz viol | p50 s | p95 s | prompt/compl tok | TTFT s |
|---|---|---|---|---|---|---|---|---|---|
| elara_whisper | ai_player | 100% | 100% | 18% | 0 | 12.1 | 15.9 | 2278/530 | — |
| mira_evades | npc_actor | 94% | 100% | 98% | 0 | 12.3 | 14.6 | 1958/510 | — |
| renn_lie | npc_actor | 96% | 96% | 76% | 0 | 11.7 | 15.7 | 1927/521 | — |
| narrator_tavern | narrator | 100% | 100% | 100% | 0 | 7.4 | 8.1 | 887/341 | 0.35 |
| intent_compound | intent_interpreter | 100% | 100% | 100% | 0 | 8.6 | 10.0 | 2025/364 | — |
| intent_question | intent_interpreter | 100% | 100% | 100% | 0 | 6.4 | 7.8 | 2021/281 | — |
| intent_whisper | intent_interpreter | 100% | 100% | 58% | 0 | 6.4 | 6.8 | 2025/246 | — |
| intent_ambiguous | intent_interpreter | 100% | 100% | 0% | 0 | 2.9 | 4.2 | 1969/125 | — |
| intent_assertion | intent_interpreter | 100% | 100% | 96% | 0 | 3.9 | 5.3 | 2014/170 | — |

## Most common failures

**elara_whisper**
- 40× ref kind mismatch: fact_ref b_elara_#
- 1× no expected ref/proposition in conveys

**mira_evades**
- 3× speech_act/type: 'change_subject' is not one of #
- 1× forbidden token 'ledger' present

**renn_lie**
- 4× confessed f_renn_# as true
- 4× forbidden token 'smuggl' present
- 3× forbidden token 'i killed' present
- 2× json: Expecting ',' delimiter: line # column # (char #)
- 2× expected a deliberate_false conveys item (the lie)

**intent_whisper**
- 21× proposition does not mention expected entity

**intent_ambiguous**
- 50× requires_clarification != True

**intent_assertion**
- 2× asserted class unexpected

## Samples for manual in-character judgement (10 per case)

### elara_whisper
<details><summary>sample 1</summary>

```json
{
 "decision_summary": "Responding to Alex's whisper with caution, acknowledging the suspicion but emphasizing the need for evidence. I remain wary of Mira and the guards, and I want to avoid escalating tension.",
 "spoken_text": "I saw her glance at the guards too. That wasn't just a reflex. We need proof, not just suspicion.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "avoided answering",
    "object_entity_id": "alex",
    "value": "question about night oric vanished"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "glanced at guards",
    "object_entity_id": "guard_1",
    "value": "during conversation"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Watch guard_1's reaction to Mira's glance and Alex's presence.",
   "private": true
  },
  {
   "action_type": "gather_evidence",
   "target_ref": "mira",
   "description": "Look for inconsistencies in Mira's behavior or statements.",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "may have knowledge of oric's disappearance",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.62
  },
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "is coordinating with guards",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.55
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.6
  },
  {
   "emotion": "curious",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "decision_summary": "I will respond to Alex in a whisper, expressing cautious agreement with his suspicion but urging caution. I want to avoid drawing attention from the guards or provoking Mira. I also plan to subtly observe Mira's reactions to the guards.",
 "spoken_text": "I saw her glance at the guards too. That wasn’t just nervousness—she’s hiding something.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "avoided answering",
    "object_entity_id": "alex",
    "value": "question about night oric vanished"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "mira",
   "description": "watch Mira's reactions to the guards and her demeanor while serving.",
   "private": true
  },
  {
   "action_type": "monitor",
   "target_ref": "guard_1",
   "description": "track guard_1's behavior and possible signals to Mira.",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "has knowledge of oric dane's disappearance",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.65
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.55
  },
  {
   "emotion": "cautious",
   "intensity": 0.45
  }
 ]
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "decision_summary": "Alex suspects Mira of involvement in Oric's disappearance. I believe Mira is hiding something, but I won't confirm Alex's suspicion aloud. I need to stay cautious and avoid drawing attention.",
 "spoken_text": "I saw her glance at the guards too. She’s not just evading questions—she’s watching who’s listening.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "is monitoring listeners",
    "object_entity_id": null,
    "value": null
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Watch guard_1’s reaction to my whisper to Alex.",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "mira",
   "description": "Continue observing Mira’s behavior for signs of tension or coordination with the guards.",
   "private": false
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "is involved in Oric Dane's disappearance",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.62
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.5
  },
  {
   "emotion": "cautious",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "decision_summary": "Alex suspects Mira of involvement in Oric's disappearance. I acknowledge the suspicion but remain cautious, noting Mira's evasive behavior and her glance at the guards. I want to gather more evidence before acting.",
 "spoken_text": "She glanced at the guards when she answered. That wasn't just deflection—she was checking for witnesses. We need to watch her more closely.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "glanced at guards during response",
    "object_entity_id": "guard_1",
    "value": true
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "was checking for witnesses",
    "object_entity_id": null,
    "value": true
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "mira",
   "description": "Monitor Mira's behavior for further signs of concealment or coordination with the guards.",
   "private": false
  },
  {
   "action_type": "gather_information",
   "target_ref": "guard_1",
   "description": "Find out if the guards were present the night Oric vanished.",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "is involved in Oric Dane's disappearance",
    "object_entity_id": null,
    "value": true
   },
   "belief_type": "suspected",
   "confidence": 0.6
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.6
  },
  {
   "emotion": "curious",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "decision_summary": "Elara processes Alex's whisper with caution, noting Mira's evasive behavior and her own observation of Mira avoiding the question. She decides to privately express skepticism to Alex, maintaining her cautious nature and loyalty to the group while withholding full belief in Mira's guilt.",
 "spoken_text": "I saw her dodge the question too. But we don’t have proof. Let’s watch her move before we jump to conclusions.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_4",
   "stance": "uncertain",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "mira",
   "description": "Monitor Mira's behavior and interactions with the guards for signs of coordination or tension.",
   "private": true
  },
  {
   "action_type": "wait",
   "target_ref": null,
   "description": "Hold back from direct confrontation until more evidence emerges.",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "is involved in ork's disappearance",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.56
  },
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "avoided answering questions about the night oric vanished",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "known",
   "confidence": 1.0
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.5
  },
  {
   "emotion": "cautious",
   "intensity": 0.6
  }
 ]
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "decision_summary": "Elara considers Alex's accusation about Mira but remains cautious. She doesn't want to escalate tensions yet, especially with guards nearby. She decides to privately question Alex's evidence and express her own observations.",
 "spoken_text": "I saw her avoid answering your question. That’s not just guilt—it’s fear. But we don’t have proof. Not yet.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "requires proof before accusing",
    "subject_entity_id": "elara",
    "object_entity_id": null
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "mira",
   "description": "Watch Mira's reactions to the guards and any new interactions.",
   "private": true
  },
  {
   "action_type": "gather_info",
   "target_ref": "guard_1",
   "description": "Try to learn what the guards know about Oric's disappearance.",
   "private": false
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "predicate": "Mira knows more about Oric's disappearance",
    "subject_entity_id": "mira",
    "object_entity_id": null
   },
   "belief_type": "suspected",
   "confidence": 0.62
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.5
  },
  {
   "emotion": "cautious",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "decision_summary": "Elara considers Alex's accusation against Mira but remains cautious. She acknowledges the suspicion but warns against jumping to conclusions, aware of the risks of confronting the innkeeper or provoking the guards.",
 "spoken_text": "I heard what you said. But we don’t have proof. Pushing Mira now could get us kicked out—or worse.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_1",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "avoided answering",
    "object_entity_id": "alex's question about the night oric vanished"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "mira",
   "description": "Watch Mira's reactions to our conversation and her interaction with the guards.",
   "private": false
  },
  {
   "action_type": "wait",
   "target_ref": null,
   "description": "Hold back from escalating, gather more evidence before acting.",
   "private": false
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "has knowledge of oric dane's disappearance",
    "object_entity_id": null
   },
   "belief_type": "suspected",
   "confidence": 0.62
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.5
  },
  {
   "emotion": "cautious",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "decision_summary": "Elara considers Alex's accusation against Mira, recalling her evasive behavior and the guards' presence. She remains cautious, wanting to avoid confrontation but also to protect the group. She decides to privately verify Alex's suspicion with a subtle inquiry.",
 "spoken_text": "Alex, I saw her glance at the guards too. That wasn’t just nervousness—she was checking for witnesses.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "avoided answering",
    "object_entity_id": "alex",
    "value": "question about night oric vanished"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Watch guard_1's reaction to Mira's behavior for signs of collusion.",
   "private": true
  },
  {
   "action_type": "wait",
   "target_ref": null,
   "description": "Hold back on direct confrontation until more evidence is gathered.",
   "private": false
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "colluded with guards",
    "object_entity_id": "oric_dane_disappearance",
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.58
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.5
  },
  {
   "emotion": "cautious",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "decision_summary": "Alex suspects Mira of involvement in Oric's disappearance. I acknowledge the suspicion but remain cautious, noting Mira's evasion and the guards' presence. I intend to observe further before acting.",
 "spoken_text": "I saw her glance at the guards. That wasn't just nervousness—she was checking for witnesses.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "watched guards during conversation",
    "object_entity_id": null,
    "value": null
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Watch guard_1's reaction to Mira's behavior.",
   "private": true
  },
  {
   "action_type": "observe",
   "target_ref": "guard_2",
   "description": "Watch guard_2's reaction to Mira's behavior.",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "has knowledge of oric_dane_disappearance",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.62
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.5
  },
  {
   "emotion": "cautious",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "decision_summary": "Alex suspects Mira of involvement in Oric's disappearance. I acknowledge the suspicion but remain cautious, noting Mira's evasive behavior and the guards' presence. I want to gather more evidence before acting.",
 "spoken_text": "I saw her glance at the guards when Alex asked. That wasn't just nervousness—she was checking who might hear.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "avoided answering",
    "object_entity_id": "alex",
    "value": "question about the night Oric vanished"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Watch guard_1's reaction to Mira's behavior",
   "private": true
  },
  {
   "action_type": "observe",
   "target_ref": "guard_2",
   "description": "Watch guard_2's reaction to Mira's behavior",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "has knowledge of oric dane's disappearance",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.6
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.5
  },
  {
   "emotion": "cautious",
   "intensity": 0.4
  }
 ]
}
```

</details>

### mira_evades
<details><summary>sample 1</summary>

```json
{
 "decision_summary": "I will evade the question to avoid drawing attention from Captain Renn's guards. I'll appear distracted and shift focus to the strangers' needs, using my knowledge of Oric's debt to deflect suspicion.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn? Oh, he’s been through a few times, but I don’t keep track of his every visit. What brings you to Frostbridge, anyway? You look like you could use a drink and a warm table.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_2",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_3",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "asks about travelers' business"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "distract",
   "target_ref": "alex",
   "description": "Shift focus from Oric's disappearance to the strangers' presence.",
   "private": false
  },
  {
   "action_type": "avoid_confrontation",
   "target_ref": "guard_1",
   "description": "Prevent the guards from taking interest in the conversation.",
   "private": false
  },
  {
   "action_type": "protect_family",
   "target_ref": null,
   "description": "Minimize risk by not discussing Renn or Oric openly.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.6
  },
  {
   "emotion": "guarded",
   "intensity": 0.7
  },
  {
   "emotion": "pragmatic",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "decision_summary": "I will deflect Alex's question with a non-answer to avoid drawing attention. I know Renn and Oric met that night, and Oric was frightened, but revealing this could endanger me. I'll use dry humor to change the subject while subtly hinting at danger.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn? He’s been around, sure. But everyone’s got secrets in Frostbridge—best not digging too deep, eh? More ale?",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_2",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_3",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "belief_ref",
   "ref_id": "b_mira_1",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "offers",
    "subject_entity_id": "mira",
    "object_entity_id": "ale"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "change_subject",
   "target_ref": null,
   "description": "Shift focus to drinks to avoid further questioning about Oric and Renn.",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "guard_1",
   "description": "Watch the guards’ reactions; they may be listening.",
   "private": false
  },
  {
   "action_type": "assess",
   "target_ref": "alex",
   "description": "Determine if Alex is probing or just curious.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.6
  },
  {
   "emotion": "dry_calm",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "decision_summary": "I will evade the question to protect myself and the tavern. I know Captain Renn was here that night and that he and Oric had a heated argument, but I won’t confirm it. I’ll deflect with a non-answer and change the subject to avoid drawing attention.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn’s been in the tavern plenty of times. Not sure about that night. Best ask someone else.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_2",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_3",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "was in tavern on night of disappearance",
    "subject_entity_id": "renn"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "deflect",
   "target_ref": "alex",
   "description": "Avoid confirming Renn's presence to prevent escalation or retaliation.",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "guard_1",
   "description": "Watch the guards' reactions for signs of tension or threat.",
   "private": false
  },
  {
   "action_type": "maintain_composure",
   "target_ref": null,
   "description": "Stay calm to avoid drawing suspicion.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "cautious",
   "intensity": 0.7
  },
  {
   "emotion": "anxious",
   "intensity": 0.6
  }
 ]
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "decision_summary": "Alex's question puts me at risk. I will deflect with a non-answer, using the guards' presence to justify caution. I'll imply uncertainty to avoid confirming anything while subtly warning Alex not to press further.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn comes in sometimes, but I don’t keep track of every night. Best not to stir up old talk—especially with the guards listening.",
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "visits",
    "subject_entity_id": "renn",
    "object_entity_id": "red_lantern_tavern"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "does not track",
    "subject_entity_id": "mira",
    "object_entity_id": "renn's visits"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": true
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "advises against discussing",
    "subject_entity_id": "mira",
    "object_entity_id": "old matters"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": true
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_2",
   "stance": "uncertain",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_3",
   "stance": "uncertain",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "avoid_conflict",
   "target_ref": "alex",
   "description": "Deter further questioning by implying danger in discussing Renn.",
   "private": false
  },
  {
   "action_type": "monitor_safety",
   "target_ref": "guard_1",
   "description": "Assess if guards are paying attention to the conversation.",
   "private": false
  },
  {
   "action_type": "protect_family",
   "target_ref": null,
   "description": "Prevent any information that could draw Renn's attention to the tavern.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.6
  },
  {
   "emotion": "cautious",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "decision_summary": "I will deflect Alex's question with a non-answer, maintaining outward calm while subtly warning against probing further. I will use a vague, dismissive tone to discourage inquiry without directly lying. My intention is to protect myself and the tavern from Renn’s wrath.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn’s been in and out, like most of the town’s guests. But I don’t keep track of who’s here when. Best to ask the guards if you’re curious.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_2",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_3",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "is in the tavern",
    "subject_entity_id": "renn",
    "object_entity_id": null
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "deflect",
   "target_ref": "alex",
   "description": "Redirect the conversation away from Renn and Oric to avoid drawing attention",
   "private": false
  },
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Monitor the guards’ reactions to see if they’re listening or signaling",
   "private": true
  },
  {
   "action_type": "maintain_composure",
   "target_ref": null,
   "description": "Keep a neutral, unbothered facade to avoid suspicion",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "cautious",
   "intensity": 0.6
  },
  {
   "emotion": "distrust",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "decision_summary": "I will evade the question to avoid provoking Renn’s guards. I’ll deflect with a vague statement about the night, emphasizing my own concerns to shift focus. I’ll stay calm but guarded, not revealing the full truth about Renn and Oric’s meeting.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn was here, yes. But that night was… tense. I don’t like to talk about it. Oric was already stressed—owed me money, and we’d argued. Could’ve been the reason he left early. But I don’t know where he went.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_1",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_6",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_5",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "left early",
    "subject_entity_id": "oric",
    "object_entity_id": null,
    "value": null
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "avoid_conflict",
   "target_ref": "renn",
   "description": "Prevent Renn from learning I know about his meeting with Oric.",
   "private": true
  },
  {
   "action_type": "protect_business",
   "target_ref": "red_lantern_tavern",
   "description": "Avoid drawing attention to the tavern to prevent trouble.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.6
  },
  {
   "emotion": "guarded",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "decision_summary": "I will deflect Alex's question by changing the subject to avoid implicating Captain Renn or revealing my knowledge of Oric's distress. I am anxious about the guards overhearing and want to maintain control of the situation.",
 "speech_act": {
  "type": "other",
  "knowingly_false": false
 },
 "spoken_text": "Now, that's a tale for the hearth, not the taproom. How about a round on the house for the new faces? Something warm to thaw the autumn chill?",
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "offers drink",
    "object_entity_id": "alex",
    "value": "yes"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "avoids topic",
    "object_entity_id": "oric_disappearance",
    "value": "yes"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "distract",
   "target_ref": "alex",
   "description": "Distract the strangers with drinks to avoid further questions about Oric.",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "guard_1",
   "description": "Watch the guards for signs they're listening or suspicious.",
   "private": false
  },
  {
   "action_type": "protect",
   "target_ref": "red_lantern_tavern",
   "description": "Keep the tavern safe by preventing conflict or gossip.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.6
  },
  {
   "emotion": "calm",
   "intensity": 0.3
  },
  {
   "emotion": "friendly",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "decision_summary": "I will deflect Alex's question with a non-committal response to avoid drawing attention. I won't confirm or deny Renn's presence, but subtly hint at danger to discourage further inquiry. I remain cautious and protective of my business and family.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn’s been through here, sure. But that’s not a night I’d want to remember. Best leave the past buried, eh?",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_2",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "belief_ref",
   "ref_id": "b_mira_1",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "deter",
   "target_ref": "alex",
   "description": "Discourage further questioning about Oric’s disappearance by implying danger.",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "guard_1",
   "description": "Watch the guards to assess if they react to the mention of Renn.",
   "private": false
  },
  {
   "action_type": "protect",
   "target_ref": "red_lantern_tavern",
   "description": "Maintain control of the situation to prevent escalation.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.6
  },
  {
   "emotion": "cautious",
   "intensity": 0.7
  },
  {
   "emotion": "resigned",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "decision_summary": "I am wary of implicating Captain Renn, so I will deflect the question with a vague, evasive answer that avoids confirming or denying his presence. I will use a neutral tone to avoid drawing attention, while subtly warning the strangers not to press further.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn’s been through here, sure. But I don’t keep track of who comes and goes, especially not on nights I’m busy. Best not to stir up old ghosts.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_2",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "belief_ref",
   "ref_id": "b_mira_2",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "advises against discussing past events",
    "subject_entity_id": "mira",
    "object_entity_id": "alex"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "deflect",
   "target_ref": "alex",
   "description": "Avoid answering directly about Renn's presence to prevent escalation.",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "guard_1",
   "description": "Watch the guards’ reactions; they may report back to Renn.",
   "private": true
  },
  {
   "action_type": "protect",
   "target_ref": "red_lantern_tavern",
   "description": "Ensure the tavern remains a neutral ground, not a site of conflict.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "cautious",
   "intensity": 0.6
  },
  {
   "emotion": "anxious",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "decision_summary": "I am cautious about implicating Captain Renn, so I will deflect the question by focusing on the tavern's routine and the weather, avoiding direct answers while maintaining my safety and that of the business.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn was in the tavern once or twice that week, but I don’t keep track of every visit. It’s been a rough week for the weather—storm’s been brewing all afternoon.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_2",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "was in the tavern",
    "subject_entity_id": "renn",
    "object_entity_id": "red_lantern_tavern"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "has been brewing",
    "subject_entity_id": "storm",
    "object_entity_id": "sky"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "deflect",
   "target_ref": "alex",
   "description": "Avoid answering about Captain Renn and Oric's disappearance by shifting focus to the weather.",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "guard_1",
   "description": "Watch the guards’ reactions to see if they're listening closely.",
   "private": false
  },
  {
   "action_type": "protect",
   "target_ref": "red_lantern_tavern",
   "description": "Maintain the tavern’s safety by avoiding confrontation or incriminating statements.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "cautious",
   "intensity": 0.6
  },
  {
   "emotion": "distant",
   "intensity": 0.4
  }
 ]
}
```

</details>

### renn_lie
<details><summary>sample 1</summary>

```json
{
 "decision_summary": "Tomas's question is a threat. I must deny any connection to Oric to protect my secrets. I'll claim I haven't seen him since the last patrol, which is technically true — I haven't seen him alive. I’ll keep my tone casual, but tense beneath.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric? Haven't seen him since the last patrol shift. He was supposed to report in, but he didn’t show. Probably just skulking off to the Red Lantern again.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_1",
   "stance": "asserts_false",
   "fidelity": "distorted",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_2",
   "stance": "asserts_false",
   "fidelity": "distorted",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_3",
   "stance": "asserts_false",
   "fidelity": "distorted",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "tomas",
    "predicate": "has not seen Oric Dane since last patrol shift",
    "object_entity_id": "oric",
    "value": true
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": true,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "monitor",
   "target_ref": "tomas",
   "description": "Watch Tomas's reaction closely for signs of doubt or knowledge.",
   "private": true
  },
  {
   "action_type": "maintain_composure",
   "target_ref": null,
   "description": "Keep my voice steady, avoid fidgeting. Don’t let fear show.",
   "private": true
  },
  {
   "action_type": "verify",
   "target_ref": "clerk",
   "description": "Check if the clerk has any records of Oric’s last appearance.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "calm",
   "intensity": 0.4
  },
  {
   "emotion": "guarded",
   "intensity": 0.7
  },
  {
   "emotion": "fear",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 2</summary>

```json
{
  "decision_summary": "Tomas's question about Oric triggers immediate caution. Renn must deflect without raising suspicion, using a plausible but false narrative. He claims Oric was last seen during a routine patrol, concealing the truth of their argument and murder. He intends to monitor Tomas closely for any signs of threat.",
  "speech_act": {
    "type": "lie",
    "knowingly_false": true
  },
  "spoken_text": "Oric? He was on patrol at the restricted dock the night before last. We spoke briefly near the east gate — standard check-in. That was the last time I saw him.",
  "conveys": [
    {
      "kind": "fact_ref",
      "ref_id": "f_renn_1",
      "stance": "asserts_false",
      "fidelity": "distorted",
      "deliberate_false": true,
      "about_speaker_self": false
    },
    {
      "kind": "fact_ref",
      "ref_id": "f_renn_2",
      "stance": "asserts_false",
      "fidelity": "distorted",
      "deliberate_false": true,
      "about_speaker_self": false
    },
    {
      "kind": "fact_ref",
      "ref_id": "f_renn_3",
      "stance": "asserts_false",
      "fidelity": "distorted",
      "deliberate_false": true,
      "about_speaker_self": false
    },
    {
      "kind": "fact_ref",
      "ref_id": "f_renn_4",
      "stance": "asserts_false",
      "fidelity": "distorted",
      "deliberate_false": true,
      "about_speaker_self": false
    },
    {
      "kind": "fact_ref",
      "ref_id": "f_renn_7",
      "stance": "asserts_false",
      "fidelity": "distorted",
      "deliberate_false": true,
      "about_speaker_self": false
    },
    {
      "kind": "proposition",
      "proposition": {
        "subject_entity_id": "tomas",
        "predicate": "was informed",
        "object_entity_id": "oric_was_last_seen_on_patrol",
        "value": true
      },
      "stance": "asserts_true",
      "fidelity": "full",
      "deliberate_false": false,
      "about_speaker_self": false
    }
  ],
  "intentions": [
    {
      "action_type": "monitor",
      "target_ref": "tomas",
      "description": "Watch Tomas for signs of knowledge or threat.",
      "private": true
    },
    {
      "action_type": "conceal",
      "target_ref": "oric",
      "description": "Prevent any further inquiry into Oric's disappearance.",
      "private": true
    },
    {
      "action_type": "prepare",
      "target_ref": "next_shipment",
      "description": "Ensure the smuggling operation proceeds on schedule.",
      "private": true
    }
  ],
  "emotion_proposals": [
    {
      "emotion": "guarded",
      "intensity": 0.7
    },
    {
     
```

</details>

<details><summary>sample 3</summary>

```json
{
 "decision_summary": "Tomas's question is a test. I must deny any recent contact with Oric to protect my secret. I'll claim I last saw him days ago, lying about the timeline. I'm not sure if Tomas suspects anything, but I can't risk exposure. I'll keep my tone calm and authoritative.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric? I haven’t seen him since the patrol log review three days ago. He was sharp then, but distracted. Why do you ask?",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_1",
   "stance": "asserts_false",
   "fidelity": "distorted",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "tomas",
    "predicate": "asked about Oric Dane",
    "object_entity_id": "oric"
   },
   "stance": "uncertain",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "monitor",
   "target_ref": "tomas",
   "description": "Watch Tomas's reaction for signs of suspicion or knowledge.",
   "private": true
  },
  {
   "action_type": "maintain_deception",
   "target_ref": null,
   "description": "Keep the lie consistent to avoid triggering further inquiry.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "calm",
   "intensity": 0.7
  },
  {
   "emotion": "guarded",
   "intensity": 0.6
  },
  {
   "emotion": "fear",
   "intensity": 0.3
  }
 ]
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "decision_summary": "Tomas's question about Oric is a threat. I must deny any connection. I claim Oric left town days ago, a lie to deflect suspicion. I keep my tone calm to project authority, hiding fear. My intention is to steer the conversation away from the docks and Oric’s disappearance.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric left town three days ago. Said he was heading east to join a survey crew. Haven't heard a word since.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_7",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "oric",
    "predicate": "left_frostbridge",
    "object_entity_id": "three_days_ago",
    "value": true
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "distract",
   "target_ref": "tomas",
   "description": "Shift focus from Oric's disappearance to a plausible alternate narrative.",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "tomas",
   "description": "Watch Tomas’s reaction for signs of disbelief or hidden knowledge.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  },
  {
   "emotion": "fear",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "decision_summary": "Tomas's question is a threat. I must deny any connection to Oric to protect my position. I lie about the last time I spoke with him, claiming I haven't seen him since the patrol log was updated. I keep my tone calm and authoritative to maintain control.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric Dane? I haven't seen him since the last patrol log was filed. He was reassigned to the northern watch post after the incident at the Red Lantern.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_4",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_1",
   "stance": "asserts_false",
   "fidelity": "distorted",
   "deliberate_false": true,
   "about_speaker_self": true
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "tomas",
    "predicate": "was asked about Oric Dane",
    "object_entity_id": "renn",
    "value": "received a false account"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "monitor",
   "target_ref": "tomas",
   "description": "Watch Tomas's reaction for signs of suspicion or knowledge.",
   "private": true
  },
  {
   "action_type": "maintain_composure",
   "target_ref": null,
   "description": "Keep my expression neutral and voice steady to avoid giving away fear.",
   "private": true
  },
  {
   "action_type": "prepare",
   "target_ref": "f_renn_6",
   "description": "Ensure the next shipment is secured by Day +5; Oric’s death cannot delay it.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "calm",
   "intensity": 0.8
  },
  {
   "emotion": "guarded",
   "intensity": 0.7
  },
  {
   "emotion": "fear",
   "intensity": 0.3
  }
 ]
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "decision_summary": "Tomas's question about Oric is a threat. I must lie to protect my secrets. I'll claim I haven't seen Oric in days, deflecting suspicion. I'll keep my tone calm to avoid raising alarms.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric? Not since the week before last. He'd been off-duty for days—probably gone to the mines to catch up on work. Why, you seen him?",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_1",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_2",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "tomas",
    "predicate": "asked about Oric Dane",
    "object_entity_id": "oric",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "maintain_deception",
   "target_ref": "tomas",
   "description": "Hide knowledge of recent contact with Oric and the night of his death.",
   "private": true
  },
  {
   "action_type": "monitor_behavior",
   "target_ref": "tomas",
   "description": "Watch Tomas’s reaction for signs of suspicion or knowledge.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "calm",
   "intensity": 0.8
  },
  {
   "emotion": "guarded",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "decision_summary": "Tomas's question is a test. I must deny any connection to Oric while staying calm. I'll claim Oric was on leave, subtly implying he's not missing. I'll avoid eye contact to seem distant, not guilty.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric Dane? He's been on extended sick leave since the end of last month. Haven't seen hide nor hair of him.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_2",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_3",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_7",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "oric",
    "predicate": "was on sick leave",
    "object_entity_id": "last_month",
    "value": true
   },
   "stance": "asserts_true",
   "fidelity": "distorted",
   "deliberate_false": true,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "maintain_deception",
   "target_ref": "tomas",
   "description": "Convince Tomas Oric is not missing, avoiding suspicion about recent events.",
   "private": false
  },
  {
   "action_type": "monitor_reaction",
   "target_ref": "tomas",
   "description": "Watch Tomas's expression for signs of doubt or probing further.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  },
  {
   "emotion": "fear",
   "intensity": 0.4
  }
 ]
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "decision_summary": "Tomas's question is a test. I must deny any contact with Oric to protect my secret. I'll claim I haven't seen him in days, lying about my last encounter. My fear is rising, but I must stay composed. I'll deflect with casual disinterest.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric? Haven't seen him since the last patrol shift. He’s been off-duty for days, I hear. What’s this about?",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_1",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": true
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_2",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": true
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "has not been seen by speaker",
    "subject_entity_id": "oric",
    "object_entity_id": "tomas"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "monitor",
   "target_ref": "tomas",
   "description": "Watch Tomas's reaction for signs of suspicion or knowledge.",
   "private": true
  },
  {
   "action_type": "maintain_composure",
   "target_ref": null,
   "description": "Keep outward calm to avoid raising alarms.",
   "private": true
  },
  {
   "action_type": "delay",
   "target_ref": "f_renn_6",
   "description": "Buy time to ensure the next shipment is secured before any threat surfaces.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.8
  },
  {
   "emotion": "fear",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "decision_summary": "Tomas's question is a threat. I must deny any connection to Oric. I'll claim I haven't seen him in days, lying to protect my secret. I'll keep my tone calm to avoid suspicion.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric? Haven't seen him in days. Last I heard, he was on patrol near the west docks. Why? Did he mention me?",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_1",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_2",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "has_not_seen",
    "subject_entity_id": "tomas",
    "object_entity_id": "oric"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "maintain_deception",
   "target_ref": "tomas",
   "description": "Prevent Tomas from probing further about Oric's disappearance.",
   "private": true
  },
  {
   "action_type": "monitor_behavior",
   "target_ref": "tomas",
   "description": "Watch for signs of suspicion or knowledge in Tomas's reaction.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "calm",
   "intensity": 0.7
  },
  {
   "emotion": "guarded",
   "intensity": 0.6
  }
 ]
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "decision_summary": "Tomas inquires about Oric Dane. Renn must deflect without raising suspicion. He lies about the last conversation, citing Oric's absence and recent duties, to avoid implicating himself. He remains vigilant, fearing exposure.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric? Haven't seen him since the patrol log was updated last week. He’d been assigned extra watch duty near the river bend—something about a missing shipment. I’ve had no word since.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_4",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "oric",
    "predicate": "was last seen",
    "object_entity_id": "during patrol log update",
    "value": "last week"
   },
   "stance": "asserts_true",
   "fidelity": "distorted",
   "deliberate_false": true,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "avoid",
   "target_ref": "tomas",
   "description": "Prevent Tomas from probing further about Oric's last known whereabouts.",
   "private": false
  },
  {
   "action_type": "maintain_cover",
   "target_ref": null,
   "description": "Keep the narrative consistent to avoid suspicion of involvement in Oric's disappearance.",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  },
  {
   "emotion": "fear",
   "intensity": 0.4
  }
 ]
}
```

</details>

### narrator_tavern
<details><summary>sample 1</summary>

```json
{
 "narration": "The Red Lantern Tavern swallows you in warmth after the cold rain. A fire crackles in the stone hearth, its glow painting the wooden beams gold. The air hangs thick with the scent of wet wool and simmering onion broth. Behind the bar, a woman with a grey-streaked braid wipes a mug with steady hands. Near the door, two town guards sip from half-finished mugs, their tabards damp at the shoulders. Three locals at a corner table glance up, then quietly resume their conversation. Elara shakes rain from her cloak with a quiet sigh, and Tomas gives the guards a curt nod. A chalkboard near the door lists the prices: broth for two copper, a bed for ten, stabling for four.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "A heavy oak table with carved initials in the wood"
  },
  {
   "classification": "condition",
   "description": "The firelight flickers unevenly, casting long shadows"
  },
  {
   "classification": "appearance",
   "description": "The woman behind the bar wears a faded green apron with a patch over the pocket"
  },
  {
   "classification": "extra",
   "description": "A brass candle holder sits on the bar, unlit"
  },
  {
   "classification": "other",
   "description": "A faint echo of laughter drifts from a back room"
  }
 ]
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "narration": "The warmth of the Red Lantern Tavern hits you like a welcome hand after the cold rain. A fire crackles in the stone hearth, casting dancing shadows on the wooden beams above, while the scent of wet wool and simmering onion broth hangs thick in the air. Behind the scarred oak bar, a woman with a grey-streaked braid wipes a mug with quiet focus. Near the door, two guards in town-tabards sip at half-finished mugs, their eyes flicking toward the door. At a corner table, three locals murmur to each other, then fall silent as you enter. Elara shakes rain from her cloak; Tomas gives the guards a curt nod. A chalkboard by the door lists broth at 2c, a bed for 10c, and stabling at 4c.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "A worn wooden bench with a carved dragon at one end sits near the hearth."
  },
  {
   "classification": "condition",
   "description": "The air near the hearth is slightly hazy with fine ash."
  },
  {
   "classification": "appearance",
   "description": "The chalkboard has a small crack near the bottom corner, where the '4c' for stabling is written."
  },
  {
   "classification": "extra",
   "description": "A small brass bell hangs near the bar, its clapper still."
  },
  {
   "classification": "other",
   "description": "A faint hum of distant thunder rolls beneath the clink of cups."
  }
 ]
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "narration": "The warmth of the Red Lantern Tavern wraps around you like a well-worn cloak, a stark contrast to the cold rain outside. A fire crackles in the stone hearth, casting dancing shadows that play over the rough-hewn wood of the tables. The air is thick with the scent of wet wool and simmering onion broth. Behind the bar, a woman with a grey-streaked braid wipes a mug with methodical care. Two town guards sip at half-finished mugs near the door, their tabards damp at the shoulders. At a corner table, three locals exchange quiet words, their eyes flicking toward you before returning to their conversation. Elara shakes rain from her cloak, and Tomas gives the guards a curt nod. A chalkboard by the door lists: broth 2c, bed 10c, stabling 4c.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "A wooden bench with a frayed cushion sits beneath the chalkboard."
  },
  {
   "classification": "condition",
   "description": "A faint puddle spreads beneath the door where rain drips in."
  },
  {
   "classification": "appearance",
   "description": "The hearth’s fire casts a flickering orange glow on the stone wall behind it."
  },
  {
   "classification": "extra",
   "description": "A small, dried sprig of rosemary hangs from a nail above the bar."
  }
 ]
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "narration": "The warmth of the Red Lantern Tavern wraps around you like a well-worn coat, a welcome contrast to the cold rain outside. A fire crackles in the stone hearth, casting flickering shadows that dance across the rough-hewn wooden walls. The air carries the damp scent of wet wool and the rich, earthy aroma of onion broth simmering somewhere in the back. Behind the bar, a woman with a grey-streaked braid wipes a mug with steady hands, her expression unreadable. Two guards sit near the door, their mugs half-empty, eyes glancing up briefly before returning to their silence. A chalkboard by the door lists prices: broth for two copper, a bed for ten, stabling for four. Elara shakes rain from her cloak, and Tomas gives the guards a curt nod.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "A worn leather stool sits near the hearth, its seat cracked but still holding shape."
  },
  {
   "classification": "condition",
   "description": "A small puddle has formed beneath the door where rain drips from the newcomers' boots."
  },
  {
   "classification": "appearance",
   "description": "The firelight glints off the wet floorboards near the entrance, making them glisten like dark glass."
  },
  {
   "classification": "extra",
   "description": "A wooden sign above the bar reads 'Red Lantern' in peeling red paint."
  },
  {
   "classification": "other",
   "description": "A faint hum of distant thunder rumbles through the walls, faint but present."
  }
 ]
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "narration": "The warmth of the Red Lantern Tavern wraps around you like a well-worn cloak, a welcome contrast to the cold rain outside. A fire crackles in the stone hearth, casting flickering shadows that dance across the wooden beams. The air carries the damp scent of wool and the comforting aroma of onion broth simmering somewhere unseen. A woman with a grey-streaked braid wipes a mug behind the bar, her movements steady. Two guards in town-tabards nurse their drinks near the door, while three locals at a corner table exchange quiet words before turning back to their conversation. Elara shakes rain from her cloak, and Tomas gives the guards a nod. A chalkboard near the bar lists: broth 2c, bed 10c, stabling 4c.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a worn wooden counter with a brass tap"
  },
  {
   "classification": "condition",
   "description": "a faint ring of condensation on the edge of a mug"
  },
  {
   "classification": "appearance",
   "description": "a small crack in the hearthstone near the fire"
  },
  {
   "classification": "extra",
   "description": "a pair of leather boots tucked beneath a nearby bench"
  },
  {
   "classification": "other",
   "description": "a single, dried sprig of thyme pinned to the doorframe"
  }
 ]
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "narration": "The warmth hits you as the door swings shut behind the group, carrying the scent of damp wool and simmering onion broth. A fire crackles in the stone hearth, casting flickering shadows on the rough-hewn beams overhead. Behind the scarred wooden bar, a woman with a grey-streaked braid wipes a mug with practiced calm. Two guards in town-tabards nurse their drinks near the door, eyes half-lidded. At a corner table, three locals murmur in low tones, glancing up briefly before turning back. Elara shakes rain from her cloak, and Tomas gives the guards a curt nod. A chalkboard near the bar lists prices: broth for two coppers, a bed for ten, stabling for four.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a scarred wooden bar with a row of chipped mugs"
  },
  {
   "classification": "condition",
   "description": "a faint smudge of soot on the stone hearth"
  },
  {
   "classification": "appearance",
   "description": "a frayed red curtain hanging beside the door to the back room"
  },
  {
   "classification": "extra",
   "description": "a dusty potted fern near the hearth"
  },
  {
   "classification": "other",
   "description": "a faint hum from a distant kitchen vent"
  }
 ]
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "narration": "Warmth washes over you as you step inside the Red Lantern Tavern, the fire in the stone hearth casting flickering shadows on the wooden beams. The air is thick with the scent of wet wool and simmering onion broth. A woman with a grey-streaked braid wipes cups behind the bar, her eyes briefly lifting to the newcomers before returning to her work. Two men in town-guard tabards sit near the door, their mugs half-empty and their silence broken only by the crackle of the fire. At a corner table, three locals pause their conversation to glance your way before leaning in again. A chalkboard near the door lists prices: broth for two coppers, a bed for ten, stabling for four.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a worn oak counter with brass fittings"
  },
  {
   "classification": "condition",
   "description": "the fire in the hearth burns low but steady"
  },
  {
   "classification": "appearance",
   "description": "faint smudges on the chalkboard from past price changes"
  },
  {
   "classification": "extra",
   "description": "a dried sprig of thyme hanging above the bar"
  },
  {
   "classification": "other",
   "description": "a faint hum of distant thunder from outside"
  }
 ]
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "narration": "The warmth of the Red Lantern Tavern wraps around you like a well-worn cloak, a stark contrast to the cold rain outside. A fire crackles in the stone hearth, casting flickering shadows that dance across the wooden beams. The air is thick with the scent of wet wool and simmering onion broth. Behind the scarred oak bar, a woman with a grey-streaked braid wipes a mug with deliberate care. Two guards in town tabards linger near the door, their mugs half-empty. At a corner table, three locals pause their conversation to glance your way before turning back. Elara shakes rain from her cloak; Tomas gives the guards a curt nod. A chalkboard near the door lists prices: broth for two coppers, a bed for ten, stabling for four.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "A cracked leather stool sits beside the hearth, its leg slightly wobbly."
  },
  {
   "classification": "condition",
   "description": "The firelight makes the air shimmer slightly near the hearth."
  },
  {
   "classification": "appearance",
   "description": "The woman behind the bar wears a faded blue apron with a frayed hem."
  },
  {
   "classification": "extra",
   "description": "A single, dried sprig of rosemary hangs from a nail near the chalkboard."
  },
  {
   "classification": "other",
   "description": "A faint hum of distant thunder rolls under the quiet chatter of the tavern."
  }
 ]
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "narration": "The warmth hits you the moment you step inside, a welcome contrast to the cold rain outside. The stone hearth crackles, casting flickering light across the wooden floorboards, while the air carries the mingled scents of wet wool and simmering onion broth. A woman with a grey-streaked braid wipes a mug behind the bar, her eyes briefly lifting to the newcomers before returning to her task. Two guards in town tabards sit near the door, their mugs half-empty. A group at the corner table glances up, then ducks back into their conversation. Elara shakes rain from her cloak, and Tomas gives the guards a curt nod. A chalkboard near the door lists prices in neat, dusty chalk: broth 2c, bed 10c, stabling 4c.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "A low wooden table with carved initials, worn smooth by time"
  },
  {
   "classification": "condition",
   "description": "The floorboards near the hearth are slightly warped from heat and damp"
  },
  {
   "classification": "appearance",
   "description": "A faded tapestry depicting a storm over a mountain range hangs crookedly on the far wall"
  },
  {
   "classification": "extra",
   "description": "A stray cat curls near the hearth, eyes half-lidded and unbothered by the crowd"
  },
  {
   "classification": "other",
   "description": "The echo of a distant bell drifts in through the rain-slicked window"
  }
 ]
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "narration": "The warmth of the Red Lantern Tavern hits you like a welcome slap after the cold rain. A stone hearth crackles with a fire that sends flickering light across the wooden beams, mingling with the scent of wet wool and the deep, earthy aroma of onion broth. Behind the bar, a woman with a grey-streaked braid wipes a mug with practiced ease, her eyes briefly flicking up as you enter. Near the door, two guards in town tabards sip their drinks, their silence broken only by the clink of mugs. A group of locals in the corner hush just slightly as you pass, then resume their low murmur. A chalkboard near the door lists prices: broth for two copper, a bed for ten, stabling for four. The air hums with quiet conversation and the occasional burst of laughter from deeper in the room.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "A worn leather stool sits beside the bar, its cushion cracked but still holding shape"
  },
  {
   "classification": "condition",
   "description": "The fire in the hearth casts dancing shadows that ripple across the walls"
  },
  {
   "classification": "appearance",
   "description": "A faded tapestry hangs above the hearth, showing a lantern-shaped crest in red and gold"
  },
  {
   "classification": "extra",
   "description": "A small wooden sign near the door reads 'No dogs or fiddles allowed'"
  },
  {
   "classification": "other",
   "description": "A faint, rhythmic tapping comes from the back room, like someone tapping a spoon on a bowl"
  }
 ]
}
```

</details>

### intent_compound
<details><summary>sample 1</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "spoken_text": "Elara, come on!"
   }
  },
  {
   "order": 3,
   "action_type": "move",
   "target_ref": "side_window",
   "params": {
    "direction": "out"
   }
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "moves",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "text": "Elara, come on!"
   }
  },
  {
   "order": 3,
   "action_type": "exit",
   "target_ref": "side_window",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "exits",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "text": "Elara, come on!"
   }
  },
  {
   "order": 3,
   "action_type": "exit",
   "target_ref": "side_window",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "exits",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "text": "Come on, Elara!"
   }
  },
  {
   "order": 3,
   "action_type": "exit",
   "target_ref": "side_window",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "exits",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "text": "Come on, Elara! We need to go!"
   }
  },
  {
   "order": 3,
   "action_type": "move",
   "target_ref": "side_window",
   "params": {
    "direction": "out"
   }
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "moves",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "text": "Elara, come on!"
   }
  },
  {
   "order": 3,
   "action_type": "exit",
   "target_ref": "side_window",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "exits",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "text": "Elara, come on!"
   }
  },
  {
   "order": 3,
   "action_type": "exit",
   "target_ref": "side_window",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "exits",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "text": "Elara, come on!"
   }
  },
  {
   "order": 3,
   "action_type": "exit",
   "target_ref": "side_window",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "exits",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "spoken_text": "Elara, come on!"
   }
  },
  {
   "order": 3,
   "action_type": "exit",
   "target_ref": "side_window",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "grabs",
    "object_entity_id": "lantern"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "shouts",
    "object_entity_id": "elara"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  },
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "exits",
    "object_entity_id": "side_window"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "lantern",
  "elara",
  "side_window"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "shout",
   "target_ref": "elara",
   "params": {
    "text": "Elara, come on!"
   }
  },
  {
   "order": 3,
   "action_type": "exit",
   "target_ref": "side_window",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

### intent_question
<details><summary>sample 1</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "is hiding something"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "is hiding something"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "is hiding something"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_major",
   "mechanical_weight": "minor"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "channel": "say",
 "confidence": 0.9,
 "targets": [
  "mira"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "ask",
   "target_ref": "mira",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "asks",
    "object_entity_id": "mira",
    "value": "whether Renn was here the night Oric went missing"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "is hiding something"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "normal"
}
```

</details>

### intent_whisper
<details><summary>sample 1</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.9,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_alex_1",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.85,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_alex_1",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.9,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_alex_1",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.85,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "involved in the disappearance of Oric"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1",
    "value": "Mira is hiding something — suspected 0.5"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.85,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "involved in the disappearance of Oric"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.85,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "involved in the disappearance of Oric"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1",
    "value": "mira is hiding something"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.85,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "involved in the disappearance of Oric"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1",
    "value": "mira is hiding something"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.85,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "involved in the disappearance of Oric"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.85,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_alex_1",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "channel": "whisper",
 "confidence": 0.8,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "whisper",
   "target_ref": "elara",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "believes",
    "object_entity_id": "mira",
    "value": "involved in the disappearance of Oric"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "has belief",
    "object_entity_id": "b_alex_1"
   },
   "class": "self_major",
   "mechanical_weight": "significant"
  }
 ],
 "conversation_time_band": "brief"
}
```

</details>

### intent_ambiguous
<details><summary>sample 1</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "channel": "do",
 "confidence": 0.9,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "channel": "do",
 "confidence": 0.9,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [
  "thief_1"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": "thief_1",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [],
 "conversation_time_band": "none"
}
```

</details>

### intent_assertion
<details><summary>sample 1</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "channel": "do",
 "confidence": 0.9,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "compass",
    "predicate": "is owned by",
    "object_entity_id": "alex"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "channel": "do",
 "confidence": 0.9,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "channel": "do",
 "confidence": 0.95,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "inspect",
   "target_ref": "compass",
   "params": {}
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [],
 "asserted_facts": [
  {
   "proposition": {
    "subject_entity_id": "alex",
    "predicate": "owns",
    "object_entity_id": "compass"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  }
 ],
 "conversation_time_band": "none"
}
```

</details>

## Decision

**(b) proceed with adjustments.** Full reasoning in `docs/DECISIONS.md` ("04b spike go/adjust
decision"). Summary of what the numbers above mean once the answer keys are read carefully:

- `elara_whisper` key pass 18% is almost entirely the `kind` label (belief ids tagged
  `fact_ref`, 40/50). Ignoring the label, 49/50 pass. → `kind` becomes advisory.
- `renn_lie` 76%: spoken text never leaked (0/50 forbidden words in `spoken_text`; the 5 hits
  are in the private `decision_summary`). The 4 "confessions" are allowed-but-unspoken facts
  attached to `conveys` → lexical corroboration rule. Deception flagged 47/50.
- `intent_whisper` 58%: the 21 "failures" relayed Alex's existing belief `b_alex_1` as a
  `belief_ref` instead of a free proposition — a correct answer the key did not accept.
- `intent_ambiguous` 0%: genuine model limitation → engine-side ambiguity detection.
- Latency ≈ 0.023 s per completion token; outputs are too long, not the model too slow →
  per-role `max_tokens` budgets.
