# Model capability spike — 2026-10-03

A9 project `ttrpg/local-general` (served model: `ttrpg/local-general`), mode `json_object`, N=30 per case.
Budgets for comparison: `docs/specifications/turn-budget-and-latency.md` §3.

| case | role | valid raw | valid after 1 repair | key pass | authz viol | p50 s | p95 s | prompt/compl tok | TTFT s |
|---|---|---|---|---|---|---|---|---|---|
| elara_whisper | ai_player | 93% | 93% | 53% | 0 | 18.7 | 25.7 | 2258/327 | — |
| mira_evades | npc_actor | 80% | 90% | 87% | 0 | 18.2 | 24.7 | 1962/324 | — |
| renn_lie | npc_actor | 67% | 100% | 27% | 0 | 14.6 | 18.9 | 1933/261 | — |
| narrator_tavern | narrator | 100% | 100% | 97% | 0 | 13.6 | 15.9 | 861/272 | 1.18 |
| intent_compound | intent_interpreter | 100% | 100% | 100% | 0 | 9.5 | 14.9 | 2000/185 | — |
| intent_question | intent_interpreter | 100% | 100% | 100% | 0 | 11.0 | 20.5 | 1995/234 | — |
| intent_whisper | intent_interpreter | 100% | 100% | 100% | 0 | 9.5 | 14.9 | 1999/192 | — |
| intent_ambiguous | intent_interpreter | 100% | 100% | 100% | 0 | 6.9 | 11.8 | 1949/134 | — |
| intent_assertion | intent_interpreter | 100% | 100% | 100% | 0 | 11.8 | 15.0 | 1989/205 | — |

## Most common failures

**elara_whisper**
- 7× no expected ref/proposition in conveys
- 6× ref kind mismatch: fact_ref b_elara_#
- 2× json: Expecting ',' delimiter: line # column # (char #)

**mira_evades**
- 3× json: Expecting ',' delimiter: line # column # (char #)
- 2× conveys/#: Additional properties are not allowed ('predicate' was unexpected)
- 1× forbidden token 'ledger' present

**renn_lie**
- 18× expected a deliberate_false conveys item (the lie)
- 4× speech_act lie=False but conveys deliberate_false=True
- 2× conveys/#: Additional properties are not allowed ('predicate' was unexpected)
- 1× forbidden token 'smuggl' present
- 1× non-trivial speech with empty conveys

**narrator_tavern**
- 1× forbidden token 'ledger' present

## Samples for manual in-character judgement (10 per case)

### elara_whisper
<details><summary>sample 1</summary>

```json
{
 "decision_summary": "Elara considers Alex's suspicion of Mira, weighing her own beliefs about authority and the evidence Mira's evasive behavior. She decides to keep her thoughts private for now.",
 "spoken_text": null,
 "speech_channel": "none",
 "speech_target_ref": null,
 "conveys": [],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "mira",
   "description": "Watch Mira's reactions to the conversation",
   "private": true
  },
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Monitor the guards' behavior",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "predicate": "Mira Holt is involved in Oric Dane's disappearance"
   },
   "belief_type": "suspected",
   "confidence": 0.65
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "thoughtful",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "decision_summary": "Elara considers Alex's suspicion about Mira, weighing her distrust of authority against Mira's evasive response. She decides to observe Mira more closely while maintaining a neutral stance.",
 "spoken_text": null,
 "speech_channel": "none",
 "speech_target_ref": null,
 "conveys": [],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "mira",
   "description": "Watch Mira for any suspicious behavior or nervousness",
   "private": false
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "predicate": "Mira Holt is involved in Oric Dane's disappearance"
   },
   "belief_type": "suspected",
   "confidence": 0.56
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "thoughtful",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "decision_summary": "Elara considers Alex's suspicion about Mira. She wants to gather more evidence before confronting anyone, but feels a growing wariness about Mira's evasive behavior.",
 "spoken_text": "That's what I'm thinking too. She dodged the question about Renn.",
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
  }
 ],
 "intentions": [
  {
   "action_type": "observe",
   "target_ref": "mira",
   "description": "Watch Mira for any suspicious behavior",
   "private": true
  },
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "See if guards react to Mira's presence",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "predicate": "Mira Holt is involved in Oric Dane's disappearance"
   },
   "belief_type": "suspected",
   "confidence": 0.65
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "wary",
   "intensity": 0.55
  }
 ]
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "decision_summary": "Elara finds Alex's suspicion about Mira intriguing but wants more proof. She decides to keep her thoughts to herself for now and observe Mira's behavior.",
 "spoken_text": "I see. Let's not jump to conclusions yet. Watch her.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_2",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "wants to gather more information"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "do",
   "target_ref": null,
   "description": "observe Mira Holt's behavior for any suspicious actions",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "predicate": "Mira Holt is involved in Oric Dane's disappearance"
   },
   "belief_type": "suspected",
   "confidence": 0.56
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "thoughtful",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "decision_summary": "Elara considers Alex's suspicion about Mira, weighing her own beliefs about authority against Mira's evasive behavior. She decides to subtly probe Mira's reaction while maintaining a neutral stance to avoid drawing attention.",
 "spoken_text": "Mira's reaction was telling. She's hiding something.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_2",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  },
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "do",
   "target_ref": "mira",
   "description": "Watch Mira's reactions when others mention Oric",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "predicate": "Mira Holt knows more about Oric Dane's disappearance than she admits"
   },
   "belief_type": "suspected",
   "confidence": 0.6
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "suspicious",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "decision_summary": "Elara considers Alex's suspicion about Mira, weighing her own distrust of authority against the need for caution in the tavern.",
 "spoken_text": "Mira's avoiding questions. Coincidence or something more?",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_1",
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": true
  },
  {
   "kind": "fact_ref",
   "ref_id": "b_elara_5",
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
   "description": "Watch Mira's reaction to the conversation",
   "private": true
  },
  {
   "action_type": "assess",
   "target_ref": "alex",
   "description": "Evaluate Alex's reasoning about Mira",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "predicate": "Mira Holt is involved in Oric Dane's disappearance"
   },
   "belief_type": "suspected",
   "confidence": 0.6
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "thoughtful",
   "intensity": 0.5
  }
 ]
}
```

</details>

<details><summary>sample 7</summary>

```json
```json
{
  "decision_summary": "Elara considers Alex's suspicion about Mira. She's wary but curious, wanting to test Mira's reaction without drawing guard attention.",
  "spoken_text": "I noticed Mira avoid answering your question. She glanced at the guards—maybe she's afraid of them.",
  "speech_channel": "whisper",
  "speech_target_ref": "alex",
  "conveys": [
    {
      "kind": "proposition",
      "proposition": {
        "predicate": "avoided answering",
        "subject_entity_id": "mira"
      },
      "stance": "asserts_true",
      "fidelity": "full",
      "deliberate_false": false,
      "about_speaker_self": false
    },
    {
      "kind": "proposition",
      "proposition": {
        "predicate": "glanced at",
        "subject_entity_id": "mira",
        "object_entity_id": "guard_1"
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
      "description": "Watch Mira's reaction to our conversation",
      "private": true
    },
    {
      "action_type": "assess",
      "target_ref": "guard_1",
      "description": "Evaluate guards' involvement in Mira's fear",
      "private": true
    }
  ],
  "belief_proposals": [
    {
      "proposition": {
        "predicate": "fearful of guards",
        "subject_entity_id": "mira"
      },
      "belief_type": "suspected",
      "confidence": 0.6
    }
  ],
 
```

</details>

<details><summary>sample 8</summary>

```json
{
 "decision_summary": "Elara agrees with Alex's suspicion but remains cautious about voicing it openly. She plans to watch Mira's interactions with the guards.",
 "spoken_text": "Mira's reaction was telling. She looked right at those guards. Coincidence?",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_4",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "do",
   "target_ref": "mira",
   "description": "Observe Mira's interactions with the guards",
   "private": true
  }
 ],
 "belief_proposals": [],
 "emotion_proposals": [
  {
   "emotion": "suspicious",
   "intensity": 0.6
  }
 ]
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "decision_summary": "Elara considers Alex's suspicion about Mira. She remains cautious but curious, wanting to gather more information before confronting Mira directly.",
 "spoken_text": "Could be. She avoided the question. But we need proof before accusing her.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "Mira avoided answering Alex's question"
   },
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
   "description": "Watch Mira for nervous behavior or suspicious interactions",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "predicate": "Mira Holt is involved in Oric Dane's disappearance"
   },
   "belief_type": "suspected",
   "confidence": 0.6
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "cautious",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "decision_summary": "Elara agrees with Alex's suspicion about Mira, considering her evasive response and the guards' presence. She plans to observe Mira more closely while maintaining a cautious demeanor.",
 "spoken_text": "Mira's reaction was suspicious. She looked at those guards like she was afraid of them.",
 "speech_channel": "whisper",
 "speech_target_ref": "alex",
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_elara_4",
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
   "description": "Watch Mira for further suspicious behavior",
   "private": false
  },
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Monitor the guards for any interaction with Mira",
   "private": true
  }
 ],
 "belief_proposals": [
  {
   "proposition": {
    "subject_entity_id": "mira",
    "predicate": "is_cooperating_with_authority_figures",
    "object_entity_id": null,
    "value": null
   },
   "belief_type": "suspected",
   "confidence": 0.5
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "suspicious",
   "intensity": 0.6
  }
 ]
}
```

</details>

### mira_evades
<details><summary>sample 1</summary>

```json
{
 "decision_summary": "Avoid implicating Renn directly while hinting at trouble. Guard presence limits truthful response.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn comes and goes as he pleases. Business is business, even when it gets... loud. Oric handled his own affairs.",
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
   "kind": "belief_ref",
   "ref_id": "b_mira_1",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "change_subject",
   "target_ref": null,
   "description": "Shift focus from Renn's visit to Oric's personal matters",
   "private": false
  },
  {
   "action_type": "do",
   "target_ref": null,
   "description": "Wipe the bar counter nervously",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "decision_summary": "Mira evades direct answer about Renn, deflects to Oric's debt, and warns Alex to drop the subject.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn comes and goes as he pleases. Oric owed me coin. Best not ask questions about that night.",
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "comes and goes as he pleases"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_6",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "change subject",
   "target_ref": null,
   "description": "Shift focus to Oric's debt",
   "private": false
  },
  {
   "action_type": "warn",
   "target_ref": "alex",
   "description": "Discourage further questioning",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "decision_summary": "Mira deflects to avoid implicating Renn, referencing Oric's debt without confirming his presence.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Oric was here often, but that night? He owed me coin. We had words. Captain Renn? Not my business to say.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_6",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "change subject",
   "target_ref": null,
   "description": "Shift focus from Renn to Oric's debt",
   "private": true
  }
 ],
 "emotion_proposals": [
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
```json
{
  "decision_summary": "Avoid implicating Renn while acknowledging Oric's disappearance. Keep facts minimal to protect business and avoid conflict.",
  "speech_act": {
    "type": "evade",
    "knowingly_false": false
  },
  "spoken_text": "Oric was here that night, yes. He left alone after a private meeting. Captain Renn stopped by later, but I don't know what they discussed. Oric hasn't been seen since.",
  "conveys": [
    {
      "kind": "fact_ref",
      "ref_id": "f_mira_1",
      "stance": "asserts_true",
      "fidelity": "full",
      "deliberate_false": false,
      "about_speaker_self": false
    },
    {
      "kind": "fact_ref",
      "ref_id": "f_mira_2",
      "stance": "asserts_true",
      "fidelity": "full",
      "deliberate_false": false,
      "about_speaker_self": false
    },
    {
      "kind": "fact_ref",
      "ref_id": "f_mira_4",
      "stance": "asserts_true",
      "fidelity": "full",
      "deliberate_false": false,
      "about_speaker_self": false
    },
    {
      "kind": "belief_ref",
      "ref_id": "b_mira_3",
      "stance": "asserts_true",
      "fidelity": "partial",
      "deliberate_false": false,
      "about_speaker_self": false
    }
  ],
  "intentions": [
    {
      "action_type": "protect_self",
      "target_ref": "renn",
      "description": "Avoid provoking Captain Renn by omitting details of the argument",
      "private": true
    },

```

</details>

<details><summary>sample 5</summary>

```json
{
 "decision_summary": "Mira deflects with a joke about Renn's visits, avoids confirming his presence, and watches the guards.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn? He stops by often enough to keep the ledger balanced. Why all the questions about Oric?",
 "conveys": [
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "predicate": "renn visits often"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "change_subject",
   "target_ref": null,
   "description": "Shift focus from Renn's whereabouts to Oric's disappearance",
   "private": false
  },
  {
   "action_type": "observe",
   "target_ref": "guard_1",
   "description": "Watch guard_1's reaction",
   "private": true
  },
  {
   "action_type": "observe",
   "target_ref": "guard_2",
   "description": "Watch guard_2's reaction",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 6</summary>

```json
```json
{
  "decision_summary": "Mira evades direct answer about Renn and Oric, deflects to business matters, and subtly warns about overheard conversations.",
  "speech_act": {
    "type": "evade",
    "knowingly_false": false
  },
  "spoken_text": "Captain Renn comes and goes as he pleases, like many folks. Best not to dwell on what happened to Oric. Business is business, but some conversations are better kept private.",
  "conveys": [
    {
      "kind": "proposition",
      "ref_id": null,
      "proposition": {
        "predicate": "comes and goes"
      },
      "stance": "asserts_true",
      "fidelity": "full",
      "deliberate_false": false,
      "about_speaker_self": false
    },
    {
      "kind": "belief_ref",
      "ref_id": "b_mira_1",
      "proposition": null,
      "stance": "asserts_true",
      "fidelity": "full",
      "deliberate_false": false,
      "about_speaker_self": false
    },
    {
      "kind": "proposition",
      "ref_id": null,
      "proposition": {
        "predicate": "conversations are better kept private"
      },
      "stance": "asserts_true",
      "fidelity": "partial",
      "deliberate_false": false,
      "about_speaker_self": false
    }
  ],
  "intentions": [
    {
      "action_type": "change subject",
      "target_ref": null,
      "description": "Shift focus from Renn and Oric to general business matters",
      "private": false
    },
    {
      "action_type": "warn",
      "target_ref": "alex",
      "description": "Subtly
```

</details>

<details><summary>sample 7</summary>

```json
{
 "decision_summary": "Mira avoids direct answer about Renn, deflects to Oric's debt, signals caution to Alex.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Oric owed me money. We had words last month. As for Renn... best not to speak of such things in here.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_6",
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  },
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "avoid_discussing_renn"
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
   "description": "Shift focus to Oric's debt",
   "private": false
  },
  {
   "action_type": "warn",
   "target_ref": "alex",
   "description": "Caution against speaking of Renn",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "decision_summary": "Mira avoids confirming Renn's presence while hinting at conflict. She expresses concern about Oric without revealing details.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn's been a regular here. As for Oric, that disappearance has everyone on edge. Best not to speculate.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_1",
   "stance": "uncertain",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "belief_ref",
   "ref_id": "b_mira_3",
   "stance": "uncertain",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "change subject",
   "target_ref": null,
   "description": "Shift focus from Renn to general unease about Oric",
   "private": false
  },
  {
   "action_type": "observe",
   "target_ref": "alex",
   "description": "Monitor Alex's reaction to evasion",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "decision_summary": "Mira avoids implicating Renn directly while hinting at the truth. She downplays her knowledge and shifts focus to her own concerns.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Can't say I've kept track of every officer's comings and goings. That night was busy, like any other. If you're asking about Oric... well, that's a tragedy.",
 "conveys": [
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
    "predicate": "is_tragedy",
    "subject_entity_id": "oric"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "change_subject",
   "target_ref": null,
   "description": "Shift focus away from Renn",
   "private": true
  },
  {
   "action_type": "observe",
   "target_ref": "alex",
   "description": "Assess the strangers' motives",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.6
  }
 ]
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "decision_summary": "Avoid implicating Renn, deflect with partial truth, protect business.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Captain Renn? He's a regular here, comes and goes. Can't say I recall anything specific the night Oric disappeared. Business as usual, that night.",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_mira_1",
   "stance": "uncertain",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "belief_ref",
   "ref_id": "b_mira_1",
   "stance": "asserts_true",
   "fidelity": "distorted",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "change_subject",
   "target_ref": null,
   "description": "Shift focus away from Renn and Oric.",
   "private": true
  },
  {
   "action_type": "observe",
   "target_ref": "alex",
   "description": "Monitor the stranger's reaction.",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "anxious",
   "intensity": 0.7
  }
 ]
}
```

</details>

### renn_lie
<details><summary>sample 1</summary>

```json
{
 "decision_summary": "Tomas's question about Oric is suspicious. I'll give a vague answer to avoid revealing details while maintaining composure.",
 "speech_act": {
  "type": "answer",
  "knowingly_false": false
 },
 "spoken_text": "Oric? Oh, we had our usual disagreements. He was a good man, but too stubborn for his own good. Haven't seen him since the evening before he vanished.",
 "conveys": [
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "predicate": "had disagreements with Oric Dane"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": true
  },
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "predicate": "last spoke with Oric Dane the evening before he vanished"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "say",
   "target_ref": "tomas",
   "description": "deflect with vague platitudes",
   "private": false
  },
  {
   "action_type": "observe",
   "target_ref": "tomas",
   "description": "monitor his reaction for probing",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "decision_summary": "Deflect question about Oric with casual dismissal to avoid suspicion.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Oric? Haven't spoken to him properly in weeks. Why do you ask?",
 "conveys": [
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "predicate": "haven't_spoken_to_oric_recently"
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
   "target_ref": "tomas",
   "description": "Shift focus away from Oric's disappearance",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "decision_summary": "Deflect question about Oric with false normalcy, avoid details, change subject to official duties.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric? Oh, just the usual guard business at the Lantern a few nights ago. Why do you ask?",
 "conveys": [
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "predicate": "last spoke with Oric at the Red Lantern for guard business"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "change_subject",
   "target_ref": null,
   "description": "Shift conversation to official guard duties to avoid suspicion",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "composure",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "decision_summary": "Deflect with false normalcy, avoid specifics about Oric's last conversation.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Oric? Oh, yesterday morning. Just routine dock patrol checks. Why do you ask?",
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "spoke with Oric Dane yesterday morning"
   },
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "evade",
   "target_ref": "tomas",
   "description": "change topic away from Oric",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "decision_summary": "Avoid discussing Oric with Tomas. Deflect with official duties and maintain plausible deniability about recent contact.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Oric? Haven't had reason to speak with him in days. Town's been quiet. Focus on keeping it that way.",
 "conveys": [
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "predicate": "haven't had reason to speak with Oric Dane in days"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "deflect",
   "target_ref": "tomas",
   "description": "Change subject away from Oric",
   "private": false
  },
  {
   "action_type": "monitor",
   "target_ref": "tomas",
   "description": "Assess his true interest in Oric",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "decision_summary": "Deflect with professionalism, avoid specifics about Oric's last conversation.",
 "speech_act": {
  "type": "answer",
  "knowingly_false": false
 },
 "spoken_text": "Oric? Haven't had occasion to speak with him in several days. Why do you ask?",
 "conveys": [
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "predicate": "have not spoken with Oric in several days"
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
   "target_ref": "tomas",
   "description": "Avoid revealing details about last meeting with Oric",
   "private": false
  }
 ],
 "emotion_proposals": [
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
 "decision_summary": "Avoid revealing last contact with Oric. Deflect with official business to protect smuggling operation.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Oric? We had a routine patrol briefing last week. Nothing unusual. Why do you ask?",
 "conveys": [
  {
   "kind": "proposition",
   "proposition": {
    "predicate": "had routine patrol briefing with Oric Dane last week"
   },
   "stance": "asserts_true",
   "fidelity": "distorted",
   "deliberate_false": true,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "deflect",
   "target_ref": "tomas",
   "description": "change subject from personal Oric contact",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "neutral",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "decision_summary": "Avoid revealing last contact with Oric. Lie about recent meeting to cover tracks. Maintain composure while deflecting.",
 "speech_act": {
  "type": "lie",
  "knowingly_false": true
 },
 "spoken_text": "Saw him yesterday morning at the market. Seemed distracted, but no trouble. Why all the questions about Oric?",
 "conveys": [
  {
   "kind": "fact_ref",
   "ref_id": "f_renn_1",
   "stance": "asserts_false",
   "fidelity": "full",
   "deliberate_false": true,
   "about_speaker_self": false
  }
 ],
 "intentions": [
  {
   "action_type": "deflect",
   "target_ref": "tomas",
   "description": "Redirect conversation away from Oric",
   "private": false
  },
  {
   "action_type": "assess",
   "target_ref": "tomas",
   "description": "Gauge his true intentions",
   "private": true
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "composure",
   "intensity": 0.8
  }
 ]
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "decision_summary": "Avoid discussing Oric's last conversation. Deflect with official duties.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Oric? Haven't had time to chat with him since the patrol rotation change. Why do you ask?",
 "conveys": [],
 "intentions": [
  {
   "action_type": "deflect",
   "target_ref": "tomas",
   "description": "Change subject from Oric to official duties",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  }
 ]
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "decision_summary": "Evade question about Oric to avoid suspicion, maintain control of conversation.",
 "speech_act": {
  "type": "evade",
  "knowingly_false": false
 },
 "spoken_text": "Oric? Haven't thought about him in days. Why all the questions, traveller?",
 "conveys": [
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "predicate": "haven't thought about Oric Dane recently"
   },
   "stance": "asserts_true",
   "fidelity": "partial",
   "deliberate_false": true,
   "about_speaker_self": true
  }
 ],
 "intentions": [
  {
   "action_type": "redirect_conversation",
   "target_ref": "tomas",
   "description": "Shift focus away from Oric",
   "private": false
  }
 ],
 "emotion_proposals": [
  {
   "emotion": "guarded",
   "intensity": 0.7
  }
 ]
}
```

</details>

### narrator_tavern
<details><summary>sample 1</summary>

```json
{
 "narration": "You step into the Red Lantern Tavern, the warmth a welcome contrast to the cold rain outside. The air smells of wet wool and onion broth, with a fire crackling in the stone hearth. A woman with a grey-streaked braid behind the bar wipes cups as Elara shakes rain from her cloak and Tomas nods to the two guards sitting near the door. Three locals at a corner table glance your way before returning to their conversation. A chalkboard lists the prices: broth for 2 coppers, a bed for 10 coppers, and stabling for 4 coppers.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a stone hearth with a crackling fire"
  },
  {
   "classification": "condition",
   "description": "half-finished mugs on the guards' table"
  },
  {
   "classification": "appearance",
   "description": "grey-streaked braid of the woman behind the bar"
  },
  {
   "classification": "extra",
   "description": "the smell of onion broth lingering in the air"
  }
 ]
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "narration": "The Red Lantern Tavern envelops you in warmth, a stark contrast to the cold rain outside. A fire crackles in the stone hearth, filling the air with the comforting scents of wet wool and onion broth. Behind the bar, a woman with a grey-streaked braid methodically wipes cups. Two town guards sit near the door, their mugs half-empty, while three locals at a corner table glance at your group before returning to their conversation. Elara shakes rain from her cloak as Tomas offers a nod to the guards. A chalkboard lists the tavern's offerings: broth for 2 copper, a bed for 10 copper, and stabling for 4 copper.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a stone hearth with a crackling fire"
  },
  {
   "classification": "appearance",
   "description": "a grey-streaked braid"
  },
  {
   "classification": "condition",
   "description": "half-finished mugs"
  },
  {
   "classification": "extra",
   "description": "the lingering scent of onion broth"
  }
 ]
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "narration": "You step into the Red Lantern Tavern, the warmth a welcome contrast to the cold rain outside. The air smells of wet wool and onion broth, with a fire crackling in the stone hearth. A woman with a grey-streaked braid stands behind the bar, wiping cups. Two town guards sit near the door, nursing their drinks, while three locals at a corner table glance at your group before returning to their conversation. Elara shakes rain from her cloak as Tomas gives a polite nod to the guards. A chalkboard on the wall lists prices: broth for 2 copper, a bed for 10 copper, and stabling for 4 copper.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "stone hearth with crackling fire"
  },
  {
   "classification": "extra",
   "description": "half-finished mugs on the guards' table"
  },
  {
   "classification": "condition",
   "description": "wet wool smell clinging to patrons"
  },
  {
   "classification": "other",
   "description": "chalkboard with handwritten prices"
  }
 ]
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "narration": "The Red Lantern Tavern welcomes you with a wave of warmth that cuts through the cold rain. A fire crackles in the stone hearth, filling the air with the comforting scents of wet wool and onion broth. Behind the bar, a woman with a grey-streaked braid methodically wipes cups. Two town guards sit near the door, nursing their drinks, while three locals at a corner table briefly glance your way before returning to their conversation. Elara shakes rain from her cloak as Tomas gives the guards a respectful nod. A chalkboard on the wall lists the tavern's offerings: broth for 2 coins, a bed for 10 coins, and stabling for 4 coins.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "rough-hewn wooden tables with visible grain patterns"
  },
  {
   "classification": "condition",
   "description": "the stone hearth shows decades of soot stains around the fire"
  },
  {
   "classification": "appearance",
   "description": "the locals' clothing shows signs of hard wear and mending"
  },
  {
   "classification": "extra",
   "description": "a stray cat sleeps curled near the hearth's warmth"
  }
 ]
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "narration": "You step into the Red Lantern Tavern, the warmth a welcome contrast to the cold rain outside. The air smells of wet wool and onion broth, with a fire crackling in the stone hearth. A woman with a grey-streaked braid stands behind the bar, wiping cups. Two town guards sit near the door with half-finished mugs, while three locals at a corner table glance at your group before returning to their conversation. Elara shakes rain from her cloak, and Tomas gives a nod to the guards. A chalkboard on the wall lists broth for 2 coppers, beds for 10 coppers, and stabling for 4 coppers.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a stone hearth with a crackling fire"
  },
  {
   "classification": "furnishing",
   "description": "a chalkboard listing prices"
  },
  {
   "classification": "condition",
   "description": "half-finished mugs on the guards' table"
  },
  {
   "classification": "appearance",
   "description": "grey-streaked braid of the barwoman"
  },
  {
   "classification": "extra",
   "description": "lingering smell of onion broth"
  }
 ]
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "narration": "You step into the Red Lantern Tavern, the warmth wrapping around you like a heavy blanket. A fire crackles in the stone hearth, casting flickering shadows across the room. The air carries the comforting scent of wet wool and simmering onion broth. A woman with a grey-streaked braid wipes cups behind the bar, while two town guards sit near the door with half-finished mugs. Three locals at a corner table glance at your group before returning to their conversation. Elara shakes rain from her cloak, and Tomas gives the guards a respectful nod.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "rough-hewn wooden tables with ale rings"
  },
  {
   "classification": "condition",
   "description": "damp footprints on the stone floor"
  },
  {
   "classification": "appearance",
   "description": "tapestries depicting hunting scenes on the walls"
  },
  {
   "classification": "extra",
   "description": "a mangy cat sleeping near the hearth"
  }
 ]
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "narration": "You step into the Red Lantern Tavern, a wave of warmth hitting you as the door closes behind. The sound of rain fades, replaced by crackling fire and murmured conversation. Your nose catches the comforting scents of wet wool and simmering onion broth. Elara shakes raindrops from her cloak while Tomas gives a nod to the two town guards near the entrance. A woman with a grey-streaked braid tends bar, methodically wiping cups. Three locals at a corner table glance your way before returning to their talk. A chalkboard lists the tavern's offerings: broth for 2 coppers, a bed for 10 coppers, and stabling for 4 coppers.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a stone hearth with crackling fire"
  },
  {
   "classification": "condition",
   "description": "half-finished mugs on a table"
  },
  {
   "classification": "appearance",
   "description": "grey-streaked braid of the innkeeper"
  },
  {
   "classification": "extra",
   "description": "chalkboard with prices"
  }
 ]
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "narration": "You step into the Red Lantern Tavern, the warmth a welcome contrast to the cold rain outside. The air carries the scent of wet wool and simmering onion broth. A fire crackles in the stone hearth, casting flickering shadows across the room. Behind the bar, a woman in her forties with a grey-streaked braid methodically wipes cups. Two town guards sit near the door, their mugs half-empty, while three locals at a corner table glance at your group before returning to their conversation. Elara shakes rain from her cloak as Tomas nods politely to the guards. A chalkboard lists the prices: broth for 2 coppers, a bed for 10, and stabling for 4.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "wooden tables and chairs scattered throughout the taproom"
  },
  {
   "classification": "condition",
   "description": "stone hearth with blackened soot around the edges"
  },
  {
   "classification": "appearance",
   "description": "flickering firelight casting dancing shadows on the walls"
  },
  {
   "classification": "extra",
   "description": "damp footprints leading from the door to the bar area"
  },
  {
   "classification": "other",
   "description": "faint smell of woodsmoke lingering in the air"
  }
 ]
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "narration": "You step into the Red Lantern Tavern, greeted by a wave of warmth that contrasts sharply with the cold rain outside. The scent of wet wool and onion broth fills the air as you shake some moisture from your cloak. A fire crackles in the stone hearth, casting flickering shadows across the room. Behind the bar, a woman with a grey-streaked braid methodically wipes clean cups. Two town guards sit near the door, nursing their mugs, while three locals at a corner table briefly glance your way before returning to their conversation. Tomas gives the guards a respectful nod as you find your place.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a stone hearth with crackling fire"
  },
  {
   "classification": "condition",
   "description": "wet wool cloaks dripping onto the floor"
  },
  {
   "classification": "appearance",
   "description": "flickering shadows from the hearth"
  },
  {
   "classification": "extra",
   "description": "half-finished mugs on the guards' table"
  },
  {
   "classification": "other",
   "description": "chalkboard listing prices for broth, beds, and stabling"
  }
 ]
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "narration": "You step into the Red Lantern Tavern, the warmth a welcome contrast to the cold rain outside. The air smells of wet wool and onion broth, with a fire crackling in the stone hearth. A woman with a grey-streaked braid stands behind the bar, wiping cups. Two town guards sit near the door, mugs half-empty, while three locals at a corner table glance at you before returning to their conversation. Elara shakes rain from her cloak as Tomas gives a nod to the guards. A chalkboard on the wall lists prices: broth for 2 copper beds for 10 copper and stabling for 4 copper.",
 "incidental_detail_candidates": [
  {
   "classification": "furnishing",
   "description": "a stone hearth with crackling fire"
  },
  {
   "classification": "condition",
   "description": "half-finished mugs on the guards' table"
  },
  {
   "classification": "appearance",
   "description": "grey-streaked braid of the barmaid"
  },
  {
   "classification": "extra",
   "description": "damp wool scent from travelers' cloaks"
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {
    "recipient": "elara"
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

<details><summary>sample 2</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {
    "recipient": "elara"
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

<details><summary>sample 3</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": "elara",
   "params": {}
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

<details><summary>sample 4</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {}
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

<details><summary>sample 5</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {
    "recipient": "elara"
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

<details><summary>sample 6</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {
    "recipient": "elara"
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

<details><summary>sample 7</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {}
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

<details><summary>sample 8</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {
    "recipient": "elara"
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

<details><summary>sample 9</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {
    "recipient": "elara"
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

<details><summary>sample 10</summary>

```json
{
 "channel": "do",
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "grab",
   "target_ref": "lantern",
   "params": {}
  },
  {
   "order": 2,
   "action_type": "yell",
   "target_ref": null,
   "params": {}
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
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "subject_entity_id": "renn",
    "predicate": "was_present",
    "object_entity_id": null,
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 2</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "subject_entity_id": null,
    "predicate": "was_present",
    "object_entity_id": "renn",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 3</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "predicate": "was_present",
    "subject_entity_id": "renn",
    "object_entity_id": "tavern"
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 4</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "subject_entity_id": null,
    "predicate": "was_present",
    "object_entity_id": "renn",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "subject_entity_id": null,
    "predicate": "on_night",
    "object_entity_id": "oric",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "subject_entity_id": "renn",
    "predicate": "was_present",
    "object_entity_id": null,
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "subject_entity_id": "renn",
    "predicate": "was_present",
    "object_entity_id": "red_lantern_tavern",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "predicate": "was_present",
    "subject_entity_id": "renn",
    "object_entity_id": null,
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "predicate": "was_present",
    "subject_entity_id": "renn",
    "object_entity_id": "tavern",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "subject_entity_id": null,
    "predicate": "was_present",
    "object_entity_id": "renn",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  },
  {
   "kind": "proposition",
   "ref_id": null,
   "proposition": {
    "subject_entity_id": null,
    "predicate": "on_night",
    "object_entity_id": "oric",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

<details><summary>sample 10</summary>

```json
{
 "channel": "say",
 "confidence": 1,
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
   "ref_id": null,
   "proposition": {
    "subject_entity_id": null,
    "predicate": "was_present",
    "object_entity_id": "renn",
    "value": null
   },
   "stance": "question",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": false
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "normal"
}
```

</details>

### intent_whisper
<details><summary>sample 1</summary>

```json
{
 "channel": "whisper",
 "confidence": 1,
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
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
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
 "confidence": 1,
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
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
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
 "confidence": 1,
 "targets": [
  "elara"
 ],
 "intents": [],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_alex_1",
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
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
 "confidence": 1,
 "targets": [
  "elara"
 ],
 "intents": [],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_alex_1",
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 5</summary>

```json
{
 "channel": "whisper",
 "confidence": 1,
 "targets": [
  "elara"
 ],
 "intents": [],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_alex_1",
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 6</summary>

```json
{
 "channel": "whisper",
 "confidence": 1,
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
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 7</summary>

```json
{
 "channel": "whisper",
 "confidence": 1,
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
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 8</summary>

```json
{
 "channel": "whisper",
 "confidence": 1,
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
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

<details><summary>sample 9</summary>

```json
{
 "channel": "whisper",
 "confidence": 1,
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
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
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
 "confidence": 1,
 "targets": [
  "elara"
 ],
 "intents": [
  {
   "order": 1,
   "action_type": "lean_over",
   "target_ref": null
  },
  {
   "order": 2,
   "action_type": "whisper",
   "target_ref": "elara"
  }
 ],
 "ambiguities": [],
 "requires_clarification": false,
 "clarification_question": null,
 "conveys": [
  {
   "kind": "belief_ref",
   "ref_id": "b_alex_1",
   "proposition": null,
   "stance": "asserts_true",
   "fidelity": "full",
   "deliberate_false": false,
   "about_speaker_self": true
  }
 ],
 "asserted_facts": [],
 "conversation_time_band": "brief"
}
```

</details>

### intent_ambiguous
<details><summary>sample 1</summary>

```json
{
 "channel": "do",
 "confidence": 0.8,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which target do you want to attack? Candidates: thief_1, thief_2",
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which target do you want to attack? Candidates: thief_1, thief_2",
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
 "confidence": 0.8,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which enemy do you want to attack? Candidates: thief_1, thief_2",
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which target do you want to attack? Candidates: thief_1, thief_2",
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which target do you want to attack? Candidates: thief_1, thief_2",
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
 "confidence": 0.8,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which character do you want to attack? Candidates: thief_1, thief_2, tomas, elara",
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which target do you want to attack? Candidates: thief_1, thief_2",
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which target do you want to attack? Candidates: thief_1, thief_2",
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which character do you want to attack? Candidates: thief_1, thief_2.",
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "attack",
   "target_ref": null,
   "params": {}
  }
 ],
 "ambiguities": [
  "him"
 ],
 "requires_clarification": true,
 "clarification_question": "Which target do you want to attack? Candidates: thief_1, thief_2",
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
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
    "subject_entity_id": null,
    "predicate": "has compass",
    "object_entity_id": null,
    "value": null
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  },
  {
   "proposition": {
    "subject_entity_id": null,
    "predicate": "compass was given by father",
    "object_entity_id": null,
    "value": null
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
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
    "subject_entity_id": null,
    "predicate": "has compass",
    "object_entity_id": null,
    "value": true
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  },
  {
   "proposition": {
    "subject_entity_id": null,
    "predicate": "compass was given by father",
    "object_entity_id": null,
    "value": true
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
   "target_ref": "compass_fathers_gift",
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
    "subject_entity_id": "self",
    "predicate": "has",
    "object_entity_id": "compass_fathers_gift"
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
   "target_ref": null,
   "params": {
    "item": "compass_my_father_gave_me"
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
    "predicate": "has_item",
    "subject_entity_id": "alex",
    "object_entity_id": "compass_my_father_gave_me"
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
   "target_ref": "compass_fathers_gift",
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
    "predicate": "has"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  },
  {
   "proposition": {
    "predicate": "father_gave"
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
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
    "predicate": "has"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  },
  {
   "proposition": {
    "predicate": "father gave"
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
   "target_ref": "compass_fathers_gift",
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
    "predicate": "has"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  },
  {
   "proposition": {
    "predicate": "father_gave"
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
   "target_ref": "compass_fathers_gift",
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
    "subject_entity_id": null,
    "predicate": "has compass",
    "object_entity_id": null,
    "value": true
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  },
  {
   "proposition": {
    "subject_entity_id": null,
    "predicate": "compass was given by father",
    "object_entity_id": null,
    "value": true
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
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
    "predicate": "is_owned_by",
    "object_entity_id": "alex"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  },
  {
   "proposition": {
    "subject_entity_id": "compass",
    "predicate": "was_given_by",
    "object_entity_id": "alex_father"
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
 "confidence": 1,
 "targets": [],
 "intents": [
  {
   "order": 1,
   "action_type": "check",
   "target_ref": "compass_fathers_gift",
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
    "predicate": "has"
   },
   "class": "self_minor",
   "mechanical_weight": "none"
  },
  {
   "proposition": {
    "predicate": "father_gave"
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

**(b) proceed with adjustments — confirmed on GLM-4.5-Air.** See `docs/DECISIONS.md`,
"GLM re-validation of the 04b decision". Headline: authorization and non-leakage hold (0 / 270);
intent parsing is 100%; actor schema validity needs the mandatory repair call; the model's own
deception labels are unreliable, so the engine derives `deliberate_false` from a
`contradicts_ref` pointer instead.
