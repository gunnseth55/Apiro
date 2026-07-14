import json

cases = [
    {
        "case_id": "unseen_case_1",
        "description": "Takotsubo Cardiomyopathy mimicking Acute STEMI",
        "target_diagnosis": "Takotsubo Cardiomyopathy",
        "vignette": "65yo female presenting with severe acute crushing chest pain and shortness of breath following the sudden death of her spouse. ECG shows ST-segment elevation in anterior leads (V2-V4). Cardiac biomarkers are mildly elevated. Urgent coronary angiography reveals completely normal coronary arteries with no thrombosis or occlusion. Left ventriculography shows apical ballooning.",
        "seed_nodes": [
            {
                "id": "s1",
                "claim": "Severe crushing chest pain and shortness of breath after intense emotional stress",
                "domain": "symptom",
                "depth": 0,
                "entropy": 0.9
            },
            {
                "id": "s2",
                "claim": "ECG shows anterior ST-segment elevation",
                "domain": "imaging",
                "depth": 0,
                "entropy": 0.8
            },
            {
                "id": "s3",
                "claim": "Coronary angiography reveals normal coronary arteries with no occlusion",
                "domain": "imaging",
                "depth": 0,
                "entropy": 0.2
            },
            {
                "id": "s4",
                "claim": "Left ventriculography shows apical ballooning",
                "domain": "imaging",
                "depth": 0,
                "entropy": 0.1
            }
        ]
    },
    {
        "case_id": "unseen_case_2",
        "description": "Guillain-Barré Syndrome mimicking Spinal Cord Compression",
        "target_diagnosis": "Guillain-Barré Syndrome",
        "vignette": "45yo male presenting with progressive bilateral leg weakness and tingling in the toes over the past 4 days. He had a diarrheal illness 2 weeks ago. Examination shows symmetrical lower extremity weakness with absent deep tendon reflexes in the ankles and knees. Sensation is relatively preserved. MRI of the entire spine is completely normal with no evidence of cord compression or mass. Lumbar puncture reveals elevated CSF protein with normal white blood cell count.",
        "seed_nodes": [
            {
                "id": "s1",
                "claim": "Progressive ascending symmetrical lower extremity weakness with absent deep tendon reflexes",
                "domain": "symptom",
                "depth": 0,
                "entropy": 0.7
            },
            {
                "id": "s2",
                "claim": "MRI of the spine is completely normal with no cord compression",
                "domain": "imaging",
                "depth": 0,
                "entropy": 0.2
            },
            {
                "id": "s3",
                "claim": "Lumbar puncture shows albuminocytologic dissociation (high protein, normal WBC)",
                "domain": "lab findings",
                "depth": 0,
                "entropy": 0.15
            }
        ]
    },
    {
        "case_id": "unseen_case_3",
        "description": "Ectopic Pregnancy mimicking Acute Appendicitis",
        "target_diagnosis": "Ectopic Pregnancy",
        "vignette": "28yo female presenting with sudden onset severe right lower quadrant abdominal pain. She feels dizzy and lightheaded. Vitals: BP 90/60, HR 115. Physical exam shows significant right lower quadrant tenderness with guarding. Ultrasound of the appendix is normal, but pelvic ultrasound reveals a complex right adnexal mass and free fluid in the pelvis. Urine beta-hCG test is positive.",
        "seed_nodes": [
            {
                "id": "s1",
                "claim": "Sudden severe right lower quadrant abdominal pain with tachycardia and hypotension",
                "domain": "symptom",
                "depth": 0,
                "entropy": 0.8
            },
            {
                "id": "s2",
                "claim": "Pelvic ultrasound reveals right adnexal mass and free fluid",
                "domain": "imaging",
                "depth": 0,
                "entropy": 0.25
            },
            {
                "id": "s3",
                "claim": "Urine beta-hCG is positive",
                "domain": "lab findings",
                "depth": 0,
                "entropy": 0.1
            }
        ]
    },
    {
        "case_id": "unseen_case_4",
        "description": "Multiple Myeloma mimicking Osteoarthritis",
        "target_diagnosis": "Multiple Myeloma",
        "vignette": "68yo male presenting with chronic lower back pain that has worsened over the last 3 months, previously attributed to osteoarthritis. He reports significant fatigue. Labs show normocytic anemia, elevated serum calcium, and elevated creatinine. X-ray of the spine shows multiple punched-out lytic bone lesions, unlike typical osteoarthritic changes. Serum protein electrophoresis demonstrates a monoclonal spike.",
        "seed_nodes": [
            {
                "id": "s1",
                "claim": "Worsening chronic lower back pain with profound fatigue",
                "domain": "symptom",
                "depth": 0,
                "entropy": 0.85
            },
            {
                "id": "s2",
                "claim": "Labs show anemia, hypercalcemia, and renal impairment",
                "domain": "lab findings",
                "depth": 0,
                "entropy": 0.4
            },
            {
                "id": "s3",
                "claim": "X-ray shows multiple punched-out lytic bone lesions in the spine",
                "domain": "imaging",
                "depth": 0,
                "entropy": 0.15
            },
            {
                "id": "s4",
                "claim": "Serum protein electrophoresis shows a monoclonal M-spike",
                "domain": "lab findings",
                "depth": 0,
                "entropy": 0.05
            }
        ]
    },
    {
        "case_id": "unseen_case_5",
        "description": "Celiac Disease mimicking Irritable Bowel Syndrome (IBS)",
        "target_diagnosis": "Celiac Disease",
        "vignette": "32yo female presenting with chronic bloating, abdominal discomfort, and diarrhea for 2 years, initially diagnosed as IBS. She also complains of an itchy, blistering skin rash on her elbows (dermatitis herpetiformis) and chronic fatigue. Lab tests reveal iron deficiency anemia. Tissue transglutaminase (tTG) IgA antibodies are highly elevated. Upper endoscopy with duodenal biopsy shows villous atrophy.",
        "seed_nodes": [
            {
                "id": "s1",
                "claim": "Chronic diarrhea, bloating, and an itchy blistering rash on elbows",
                "domain": "symptom",
                "depth": 0,
                "entropy": 0.6
            },
            {
                "id": "s2",
                "claim": "Labs show iron deficiency anemia and highly elevated tTG-IgA antibodies",
                "domain": "lab findings",
                "depth": 0,
                "entropy": 0.1
            },
            {
                "id": "s3",
                "claim": "Duodenal biopsy shows villous atrophy",
                "domain": "imaging",
                "depth": 0,
                "entropy": 0.05
            }
        ]
    }
]

with open("data/unseen_cases.json", "w") as f:
    json.dump(cases, f, indent=2)
