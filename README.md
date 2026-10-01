# Interactive Generative Video Lessons

## Project Context & Abstract

**Course:** ICS 591: Capstone: Building Secure Intelligent Computing Systems
**Team:** Thomas Kojo Quarshie, Naa Lamle Boye, Nicole Nanka Bruce, Elijah Boateng

**Concept:**
Interactive Generative Video Lessons is a learning product designed to generate interactive video lessons from student-supplied context, such as prompts or documents. It is tailored for students in a Ghanaian learning setting, with an initial focus on mathematics and programming.

**Interaction Model:**
Students can pause the lesson to ask questions via speech, text, or by visually selecting and marking an area on the screen. The system contextualizes the question against the current visual, adapts the explanation (for example, dynamically re-rendering a fraction explanation to use mangoes), and seamlessly resumes the lesson.

**Core Features:**
- Context-to-lesson generation
- Interruptible playback
- Illustrative visual continuations
- Robust lesson player

## Architecture & Technical Scope

### Learner Experience
An Interactive Lesson App connected via HTTPS and realtime channels through an API Gateway.

### Platform Services
- Session and Lesson Orchestrator
- Base Lesson Planning Engine
- Verification and Policy Layer
- Lesson and Scene Compiler
- Content Ingestion and Safety
- Learned Adaptation Component
- Context Builder
- Asset Delivery Service

### Infrastructure
- Rendering Job Queue
- Approved Knowledge Base
- Asset Cache
- Telemetry Store
- Foundation Model Provider
- Lesson Scene/Session State Database

### Measurement & Evaluation
The system relies on a formalized measurement stub matrix to track degradation signals, ensuring:
- Interaction mapping completeness
- Malicious content detection
- Mathematical correctness
- Accurate referent resolution
- Reliable end-to-end rendering

## Repository Structure

- `spec/`: Scope and architecture specifications.
- `backend/`: Python-based API (using FastAPI) handling the learned components and orchestrator.
- `frontend/`: Cross-platform client (using Flutter) serving as the Interactive Lesson App.
- `.github/workflows/`: CI/CD pipelines enforcing Test-Driven Development (TDD).
