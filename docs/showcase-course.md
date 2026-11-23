# Showcase course setup sheet

Everything to type into Moodle to build the two showcase courses: **Amplifier Showcase** (UEEEC0066) and **Digital Electronics Showcase** (UEEEC0069). Each block is ready to paste.

## Before you start

- Run `deploy/deploy.sh`, so the tool has all ten items.
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

# Course 1: Amplifier Showcase

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

- **Pick:** Power Amplifier Current Flow Simulator
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

# Course 2: Digital Electronics Showcase

## Course

**Course full name:** Digital Electronics Showcase
**Course short name:** DIGSHOW

**Course summary:**

> Interactive practice and assessment for digital electronics. Students derive and simplify logic circuits step by step on the circuit itself, then build and fault-find the same circuit on a simulated breadboard. Quiz scores go straight to the Moodle gradebook.

## Section: Logic Circuits

**Section summary:**

> Combinational logic, from Boolean expressions to a working circuit on the bench.

---

### Subsection: Boolean Algebra

**Description:**

> Boolean expressions for each gate, DeMorgan's theorems and simplification. Then the same three-input circuit is derived on paper, built on a breadboard and fault-found with a logic probe.

The five activities follow one path: learn the rules, derive a circuit, build it, find a fault in it. Activities 3, 4 and 5 all use the same circuit, Z = A·B·C̄ + B̄·C. Keep them in this order.

#### Activity 1: Knowledge Basics

- **Pick:** Boolean Algebra: Knowledge Basics
- **Graded:** yes. 9 questions.

**Description:**

> How Boolean algebra differs from ordinary algebra, the expression for each of the seven gates, writing the expression for a circuit, truth tables, DeMorgan's theorems and simplifying to sum-of-products.

#### Activity 2: Step Through the Circuit (A, B)

- **Pick:** Step Through the Circuit (A, B)
- **Graded:** yes. 6 steps.

**Description:**

> A two-input circuit built only from NAND and NOT gates. Label each point on the circuit, work out every gate's output, apply De Morgan's law, cancel the double negations, and check the result with a truth table.

#### Activity 3: Step Through the Circuit (A, B, C)

- **Pick:** Step Through the Circuit (A, B, C)
- **Graded:** yes. 6 steps.

**Description:**

> A three-input circuit built from 7408, 7402 and 7400 ICs, with pin numbers as in the lab. Derive Z level by level, simplify it with De Morgan's law, and complete the truth table you would check your measured outputs against.

#### Activity 4: Logic Circuit on a Breadboard

- **Pick:** Logic Circuit on a Breadboard: Simulator
- **Graded:** no. Set completion to **View**.

**Description:**

> The circuit from Activity 3, built on a breadboard as in the lab. Flip the A, B and C switches and watch the level on every wire and pin. Tap holes and pins to see how they connect, and step through a change one stage at a time.

#### Activity 5: Fault Finding on a Breadboard

- **Pick:** Fault Finding on a Breadboard: Simulator
- **Graded:** no. Set completion to **View**.

**Description:**

> The same breadboard circuit with one hidden fault. Compare the output with the truth table, probe holes and pins with a logic probe, and track down the fault the way you would on the bench.

---

## Checking it works

1. In a private window, log in as `student1`.
2. Open one graded quiz and finish it. The green "sent to the Moodle gradebook" note should appear.
3. As admin, open **Grades** for the course. The score should appear in that quiz's column.
4. If you set completion conditions, the student's course page now shows a tick next to that quiz.
