# Decisions

We keep only Base Lesson Planning Engine and Lesson Adaptation Builder inside the learned boundary because they propose plans. Verification and state updates remain outside so unchecked responses cannot mutate the lesson. We use a deterministic mock for local repeatability. Pointer references use scene-object IDs; operations are declarative and allowlisted. Technical execution checks cannot establish learning benefit; that needs a controlled evaluation.
