from sentence_transformers import CrossEncoder

model = CrossEncoder('cross-encoder/nli-MiniLM2-L6-H768')
scores = model.predict([
    ("A patient is diagnosed with Acute Pancreatitis.", "The patient presents with the clinical finding of epigastric."),
    ("A patient is diagnosed with Acute Pancreatitis.", "The patient presents with the clinical finding of jaundice."),
    ("A patient is diagnosed with Acute Pancreatitis.", "The patient presents with the clinical finding of normal."),
])
# output: contradiction, entailment, neutral
labels = ['contradiction', 'entailment', 'neutral']
for i, s in enumerate(scores):
    idx = s.argmax()
    print(f"Test {i+1}: {labels[idx]} (score: {s[idx]:.3f})")

