import json
import asyncio
from apiro.patient.context import extract_patient_context

async def main():
    with open('/home/theroid/PycharmProjects/Apiro/data/pmc_cases.json', 'r') as f:
        cases = json.load(f)
        
    case = None
    for c in cases:
        if c['case_id'] == 'pmc_case_10':
            case = c
            break
            
    if not case:
        print("Case not found")
        return
        
    print(f"Vignette:\n{case['vignette']}\n")
    context = extract_patient_context(case['vignette'])
    from dataclasses import asdict
    print("Extracted Context:")
    print(json.dumps(asdict(context), indent=2))

if __name__ == '__main__':
    asyncio.run(main())
