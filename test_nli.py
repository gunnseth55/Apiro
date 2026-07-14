from sentence_transformers import CrossEncoder

model = CrossEncoder('cross-encoder/nli-MiniLM2-L6-H768')
scores = model.predict([
    ("The patient has Acute Pancreatitis.", "The patient has epigastric."),
    ("A patient is diagnosed with Acute Pancreatitis.", "The patient presents with epigastric pain."),
    ("The diagnosis is Acute Pancreatitis.", "The symptom is epigastric."),
])
# output: contradiction, entailment, neutral
labels = ['contradiction', 'entailment', 'neutral']
for i, s in enumerate(scores):
    idx = s.argmax()
    print(f"Test {i+1}: {labels[idx]} (score: {s[idx]:.3f})")

