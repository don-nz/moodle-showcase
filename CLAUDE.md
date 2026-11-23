# Quiz Showcase: LTI tool server for Moodle

## What this project is for

Don wants to move into educational software full time. His way in is the interactive electronics site he has built for his TAFE NSW Cert III course. This repo is the **business side** of that: a demo for colleges, aiming to sell **bespoke quizzes and simulators for their courses**.

The demo runs on two Ubuntu Server VMs Don has set up. Ask him what state they're in before assuming anything:

- **VM 1: Moodle.** A showcase course that colleges can look around.
- **VM 2: this tool server.** It hosts the quizzes and simulators and connects to Moodle over **LTI 1.3**.

## The content lives in another repo

The quizzes and simulators are authored in a separate repo: `/mnt/ldata/development/tafe/electronics`. That repo is the **single source of truth**. Don keeps authoring there exactly as he does now. This repo pulls in a *built* copy, through a build step or a git submodule; work out which with Don. Never edit content here.

Structure of the content repo, as far as this project needs it:

- `cert_iii/assets/`: shared files.
  - `quiz-engine.js`: the quiz engine. Each quiz page defines a `QUESTIONS` array; fields like `text`, `options` and `working` are **functions**, by design, so values can be randomised. `RESET_EXTRA` regenerates random values on restart.
  - `quiz-common.css`: the site palette and the colour classes (`.colour-resistor`, `.colour-cap`, `.colour-voltage`, `.colour-current`, `.colour-power`, `.colour-gain`…).
  - `shapes.js`: shared SVG symbols.
  - `frac()` / `sqrt()` in the engine produce stacked fractions and covering root bars for worked solutions.
- `cert_iii/UEEEC0066/`: Amplifier Configurations (BJT amps, power amps, op-amps). It includes the power-amp current-flow simulators in `resources/`.
- `cert_iii/UEEEC0069/`: Digital Electronics (gates, flip-flops, counters, simulators, a breadboard fault-finding simulator).
- `tools/build_college.py`: builds **self-contained single-file** copies of pages in the TAFE NSW look. The outputs go into each unit's `college/` folder. These single files are the natural thing to serve from this tool, and to package.
- Pages are plain HTML, CSS and JavaScript with no build framework. They work from `file://`.

## The plan

### Delivery: LTI 1.3, not just SCORM

- **LTI 1.3:** a college adds this tool to their Moodle course. The content stays on Don's server, so colleges never hold the files. Access can be switched off when a licence ends, usage can be seen, and grades go back to Moodle's gradebook through **LTI Assignment and Grade Services (AGS)**. This is the main protection and selling point.
- **SCORM:** quick and fine for a giveaway demo, but the college keeps the files, so it protects nothing.

### Protection, strongest first

1. **Host and deliver through LTI**, as above.
2. **Check answers on the server.** Today every answer sits in the page's JavaScript, which is fine for practice but not for assessment, because a student can read it. The server should generate the question values, keep the answers and mark them. The simulators have to calculate in the browser to animate, so for those only items 1, 3 and 4 apply.
3. **Minify and obfuscate** (terser, javascript-obfuscator) and make **per-college builds with a hidden watermark**. This deters casual copying and traces leaks; it doesn't truly protect.
4. **Licence terms and copyright notices.** Colleges are institutions with procurement rules, so a contract does more than code.

Anything that runs in the browser can be read. Never present obfuscation or a separate server as hiding the JavaScript.

### Stack (decided 2026-11-17)

- Python with **FastAPI**, plus **our own small LTI 1.3 layer** (`app/lti.py`) on top of PyJWT.
  - PyLTI1p3, the only Python LTI library, has been unmaintained since Nov 2022, has no FastAPI support and no dynamic registration, so it isn't used.
  - The layer covers OIDC login, launch validation, content selection (Deep Linking 2.0), AGS scores and dynamic registration. `tests/test_lti.py` exercises each check against a fake Moodle, so keep those tests passing when you change it.
- **SQLite** holds platforms, deployments, launches and attempts.
  - The private key, session secret and database live in `TOOL_DATA_DIR`, never in git.
- **Content arrives through a build step:** `scripts/build_content.py` runs the content repo's `build_college.py` for each quiz in `content/manifest.json` and commits the output to `content/built/`.
- **Scores reach the server without editing content:** the tool adds a script to each served quiz page. The script wraps the engine's `showSummary`/`resetQuiz` and posts the score once per attempt.
- **Servers are built by script:** `deploy/setup-moodle.sh` and `deploy/setup-tools.sh` set up fresh Ubuntu servers behind Cloudflare Tunnels (decided 2026-11-23), following `docs/server-setup.md`. Keep the scripts and the guide in step, since they're meant to work unchanged on a hosting provider.
- **Grade sync is AGS 2.0. It has not yet been tested against the real Moodle.** See README.md for setup.

## First milestone

**One quiz end to end:**

1. Moodle on VM 1 launches it through LTI 1.3.
2. The tool on VM 2 serves the quiz.
3. The student answers.
4. The score lands in the Moodle gradebook through AGS.

Suggested phasing:

- **Phase 1:** serve an existing built quiz page inside the LTI launch. The page reports its final score to the tool, for example with `postMessage` to a small wrapper and then a POST to the server, and the tool passes the grade back through AGS. Answers are still checked in the browser at this stage, which is fine for the demo.
- **Phase 2:** move generation and marking for that quiz to the server.

Good first candidates are a short randomised UEEEC0066 quiz, such as `term-2/power-amps/fault-finding/power_amp_fault_finding_knowledge_basics.html`, plus one simulator as a show piece (the breadboard fault finder or the 741 power-amp simulator).

## Working with Don

- **Commits:** when he asks for a commit message, give just the message text, ready to paste into the VS Code git plugin, not a git command. Commit only when he asks.
- **Privacy:** never put his name, email or project details into requests to outside services.
- **Explanations:** keep them plain, with short bullets; he's happy to be asked brief questions when something is genuinely his decision.
- **Content conventions** (they live in the content repo, but matter for demos and new bespoke work):
  - Put a visual on as many quiz questions as possible, but never label the answer on the diagram.
  - For UEEEC0066 hand working, use V<sub>BE</sub> = 0.6 V (diodes 0.6 V), treat input bases as 0 V and ignore base currents.
  - Show worked solutions with stacked fractions and colour-coded components and quantities.
  - Show each device's symbol with behaviour questions, and add waveforms where behaviour happens over time.
- **The content repo on GitHub:** Don was advised to make it **private**; check this. This repo must be private too.
