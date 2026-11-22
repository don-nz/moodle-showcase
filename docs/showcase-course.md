# Showcase course setup sheet

Everything to type into Moodle to build the Amplifier Showcase course. Each block is ready to paste.

## Before you start

- Run `deploy/deploy.sh`, so the tool has all five items.
- In the tool's settings, turn on **Supports Deep Linking** and set the Content Selection URL. README.md, step 7, covers this.

## For every activity

1. In the subsection, open **Add content → Activity or resource → Quiz Showcase**.
2. Fill in **Activity name**.
3. Click **Select content** and pick the item named below. The list is grouped by topic.
4. Paste the **Description**, and tick **Display description on course page**.
5. Set **Completion conditions**:
   - Graded quiz: **Receive a grade**.
   - Simulator: **View**.
6. Click **Save and return to course**.

Moodle sets up the gradebook column itself, out of 100. A score of 7 / 12 shows as 58.33.

---

## Course

**Course full name:** Amplifier Showcase
**Course short name:** AMPSHOW

**Course summary:**

> Interactive practice and assessment for amplifier configurations. Every quiz is built around a circuit diagram, and the calculation questions show a full worked solution with colour-coded components and quantities. Scores go straight to the Moodle gradebook.

## Section: Power Amps

**Section summary:**

> Power amplifiers from the output devices back to the input: output stage configurations, the stages of a complete amplifier, and finding faults in a working circuit.

---

### Subsection: Output Configurations

**Description:**

> Class B and class AB output stages, Darlington and composite pairs, driver transistors, VBE multipliers and ways of reducing crossover distortion.

#### Activity 1: Knowledge Basics

- **Pick:** Output Configurations: Knowledge Basics
- **Graded:** yes. 12 questions.

**Description:**

> Identify output configurations from their circuits and explain how each part of the stage works: biasing, Darlington and composite pairs, driver transistors, VBE multipliers, emitter resistors and complementary MOSFET outputs.

#### Activity 2: Circuit Analysis

- **Pick:** Output Configurations: Circuit Analysis
- **Graded:** yes. 5 calculation questions.

**Description:**

> Work out the DC conditions and output power of a class AB stage on a split supply: quiescent current, bias voltages, collector voltage and maximum load power. Each answer comes with a worked solution.

---

### Subsection: Power Amp Stages

**Description:**

> How a complete power amplifier fits together: differential input, voltage amplifier, output stage and the global negative feedback that sets the gain.

#### Activity 3: Knowledge Basics

- **Pick:** Power Amplifier Stages: Knowledge Basics
- **Graded:** yes. 7 questions.

**Description:**

> Name each stage of a complete amplifier and its job, find the feedback network on the circuit, and calculate the closed-loop voltage gain.

#### Activity 4: Current Flow Simulator

- **Pick:** Power Amplifier Current Flow Simulator (under Simulators)
- **Graded:** no. Set completion to **View**.

**Description:**

> An interactive 741-driven NPN/PNP push-pull amplifier. Flip switches on the circuit to watch the current flow and see what a meter would read, under DC conditions or with an AC signal. Tap a transistor to see its voltages worked out step by step, using either course values or the simulator's actual values.

---

### Subsection: Power Amp Fault Finding

**Description:**

> Diagnosing faults in a complete IC power amplifier, plus heatsinking and output power.

#### Activity 5: Knowledge Basics

- **Pick:** Power Amplifier Fault Finding: Knowledge Basics
- **Graded:** yes. 9 questions.

**Description:**

> Predict what each component fault does to the amplifier's output, match faults that look the same, and cover heatsink mounting, output coupling and maximum output power.

---

## Checking it works

1. In a private window, log in as `student1`.
2. Open one graded quiz and finish it. The green "sent to the Moodle gradebook" note should appear.
3. As admin, open **Grades** for the course. The score should appear in that quiz's column.
4. If you set completion conditions, the student's course page now shows a tick next to that quiz.
