# Routing Desk: Preparation Guide for the Presentation

This guide explains the whole project from start to finish in plain words. Read it once from top to bottom, then use the judge questions (section 11) and the cheat sheet (section 12) to practise.

A quick rule for the day: every number in this guide is checked against the trained system. If a judge asks for a number that is not here, it is fine to say "we did not measure that". Do not guess.

---

## 1. The problem statement

### The exact wording

> "Develop an NLP-based system that automatically understands and classifies customer banking queries into relevant categories such as payments, cards, loans, account issues, and fraud. The system will help banks efficiently route customer queries to the appropriate service or department, reducing manual effort and improving response time."

"NLP" stands for Natural Language Processing. It simply means teaching a computer to work with human language, such as the messages people type.

### What it means in plain words

Banks get many customer messages every day. They come through the app, the website, chat, email and phone. Each message is about something different. One person's card has not arrived. Another wants to know their loan repayment. Someone else sees a payment they never made.

Today, a person often has to read each message and decide which team should deal with it. The task is to build a computer system that does this first reading and sorting automatically.

### Who suffers today

- **Customers wait.** Their message sits in a queue until someone reads it and passes it on. If it goes to the wrong team, it waits again.
- **Staff do repetitive work.** Reading and sorting the same kinds of messages all day is slow and boring, and tired people make mistakes.
- **Fraud cases get delayed.** Some messages are urgent. If someone is stealing a customer's money, every hour counts. A fraud message stuck behind hundreds of ordinary questions is a real problem.

### What "routing" means

Routing means sending each message to the right team.

Think of a post office sorting desk. Letters arrive in one big pile. A sorter reads each address and drops the letter into the right bag: this one to London, this one to Manchester. Urgent parcels get a red sticker and go first.

Our system is that sorting desk for bank messages. It reads the message, decides which team it belongs to, and puts an urgency sticker and a deadline on it.

---

## 2. What we built

### In one paragraph

We built a working system called Routing Desk. A customer message goes in. The system first hides any personal details, like card numbers. It then decides which of the 5 categories the message belongs to (Payments, Cards, Loans, Account issues or Fraud) and which of 83 specific topics it is about. A set of business rules double-checks for fraud and other special cases. Then it creates a ticket for the right team, with a priority and a response deadline. Bank staff ("agents") work through these tickets in an inbox. When an agent corrects a mistake, the correction is saved and used to teach the next version of the system. It all comes with a web app, a way for other bank systems to connect to it, and automatic tests.

### The journey of one message

1. **A customer writes:** "My card 4539 1488 0343 6467 was skimmed at the ATM."
2. **Hide personal details.** The card number is replaced with [CARD] before anything is stored.
3. **Clean the text.** Everything goes to lower case, and amounts and numbers are replaced by placeholders.
4. **Turn the words into numbers** so the computer can compare this message with the ones it learned from.
5. **Two models make their guesses.** One picks the category (which team). The other picks the exact topic (what the problem is).
6. **Business rules check the result.** Here the word "skimmed" is a strong fraud phrase, so the message goes to Fraud no matter what.
7. **A ticket is created:** Fraud & Security Team, urgent, respond within 1 hour.
8. **An agent picks it up** in the inbox. If the team was wrong, the agent moves it, and the system learns from that.

---

## 3. The data

### What the system learned from

A "model" is the part of the system that has learned patterns from examples and uses them to make guesses about new messages. A "dataset" is the collection of examples it learns from.

Our main dataset is **Banking77**. It was published by **PolyAI** (Casanueva et al., 2020). It is free to use under the **CC BY 4.0** licence. It contains real customer questions written to a digital bank.

- **13,083 messages in total:** 10,003 for training and 3,080 for testing.
- Each message is labelled with one of **77 detailed topics**, for example "card arrival", "lost or stolen card" or "exchange rate".

### Why we chose Banking77

- **Real wording.** The messages have typos and short chat-style writing, just like real customers.
- **Banking-specific.** Every message is about banking, not general chat.
- **Free and public.** Anyone can download it and check our work.
- **Already labelled.** Someone has already marked the correct topic for each message, so we can teach and test the system.
- **Widely used** for exactly this kind of task.

### Grouping 77 topics into 5 categories

The problem statement asks for 5 categories. Banking77 has 77 topics. So we grouped each topic into one category:

| Category | Number of topics | Examples |
|---|---|---|
| Payments | 37 | transfers, top-ups, refunds, exchange rates, fees, pending payments |
| Cards | 24 | ordering, activating, PINs, ATMs, card not working |
| Account issues | 10 | identity checks, personal details, passcode, closing an account |
| Fraud | 6 | payments, withdrawals or direct debits the customer doesn't recognise; compromised card; lost or stolen card; lost or stolen phone |
| Loans | 0 | none |

### The loan gap and how we filled it

Banking77 has **no loan questions at all**. But the problem statement asks for loans. So we had to create them.

- We wrote **60 loan question templates** across **6 loan topics**: applying, application status, interest and fees, repayments/EMI, paying off/closing, and changes and statements.
- We filled the templates with different loan types, amounts and time periods to make many different questions.
- **Test templates are kept separate from training templates.** That means the test only contains loan wording the system never saw while learning.

**The honest caveat:** these loan messages are cleaner than real customer messages. So the loan score is optimistic. Say this openly before a judge asks.

With the 6 loan topics added, the system knows **83 topics in total** (77 from Banking77 plus 6 loan topics).

### Cleaning the data

Before training, we:

- removed empty rows,
- removed duplicates,
- removed any sentence that appears in both the training set and the test set (so the test is fair).

### Final sizes

| | Payments | Cards | Account issues | Fraud | Loans | Total |
|---|---|---|---|---|---|---|
| Training | 5,338 | 2,701 | 1,137 | 799 | 544 | 10,519 |
| Test | 1,480 | 959 | 400 | 240 | 113 | 3,192 |

The 10,519 training messages are made of 9,974 from Banking77, 544 loan messages and 1 agent correction (a real example of the learning-from-corrections feature).

### The imbalance and how we handled it

About half the training data is Payments. Loans and Fraud are small. A lazy system could just guess "Payments" a lot and still look good. To stop this, the system is told to give the small categories equal importance, so it does not ignore them. This matters most for Fraud, which is small but the most important to get right.

---

## 4. How it works

### Stage 1: Hiding personal details

Before anything is stored or read by the model, the system finds card numbers, account numbers, IBANs, sort codes, email addresses and phone numbers, and replaces them with placeholders like [CARD]. The model never needs the real number to know the message is about a card.

### Stage 2: Cleaning the text

Everything is turned into lower case, so "Card" and "card" are treated the same. Amounts of money and other numbers are replaced by placeholders, because "£50" and "£500" mean the same kind of question.

### Stage 3: Turning words into numbers

Computers cannot read words, but they can compare numbers. So each message is turned into a list of numbers. The system looks at:

- **single words** ("card", "arrived"),
- **pairs of words** ("not arrived", "exchange rate"),
- **small chunks of letters**, which helps with typos. "recieve" and "receive" share most of their letter chunks.

Words that are common everywhere count for less, and words that are special to a message count for more. The technical name for this is **TF-IDF**. If a judge uses that term, that is what it means.

### Stage 4: The two models

- **Category model:** picks one of the 5 categories. This decides the team.
- **Topic model:** picks one of the 83 specific topics. This tells the agent exactly what the issue is, so they don't have to work it out.

Both use a method called **Logistic Regression**. In plain words: it gives each word or word pair a weight for each category, adds them up, and turns the totals into a percentage for each category. The highest percentage wins. Because it gives a percentage, we also know how sure it is.

### Stage 5: Business rules

Rules sit on top of the models. They live in a settings file, so the bank can change them without retraining anything.

- **Manual review.** If the system is less than **60%** sure, a person checks the message.
- **Fraud safety net, two levels.**
  - *Strong phrases* such as "skimmed", "cloned", "scam", "hacked", "wasn't me" and "didn't authorise" **always** send the message to Fraud.
  - *Weaker words* such as "fraud", "suspicious" and "stolen" only send it to Fraud if the model also gives fraud **at least 10%**. This stops every message that merely mentions one of these words from flooding the fraud team, while still catching real cases.
- **Priority boosts.** Bereavement and formal complaints are raised to high priority. Account takeover is raised to urgent.

### Stage 6: Tickets with deadlines

Each message becomes a ticket with a team, a priority and a response deadline:

| Category | Team | Priority | Respond within |
|---|---|---|---|
| Fraud | Fraud & Security Team | Urgent | 1 hour |
| Payments | Payments & Transfers Desk | High | 8 hours |
| Cards | Card Services | Normal | 24 hours |
| Account issues | Account Services | Normal | 24 hours |
| Loans | Lending Team | Normal | 48 hours |
| System unsure | Manual review (General Support) | - | 24 hours |

### Stage 7: The agent inbox and learning from corrections

Agents work through tickets in an inbox sorted by urgency and deadline. If an agent decides a ticket belongs to a different team and moves it, that correction is saved. The next time the model is trained, it learns from those corrections. So the system gets better from the everyday work of the staff.

### Stage 8: The release check

Every new version of the model must pass a set of minimum scores before it goes live. If it fails, the old version stays. This stops a worse model from slipping into use. The exact thresholds are in section 6.

---

## 5. How we chose the model

### Training and testing

- **Training** means showing the system thousands of messages with the right answer, so it can learn the patterns.
- **Testing** means giving it messages it has never seen and checking its answers.

### Why a separate test set matters

It is like a school exam. If students see the exact exam questions in advance, a high score proves nothing. The test set is our sealed exam paper. We never used it to make choices. We only opened it at the end to report the score.

### Practice rounds

To choose between methods without touching the exam paper, we used practice rounds. The training data is split into 5 parts. Each part takes a turn being the quiz while the other 4 are used for learning. The technical name is **5-fold cross-validation**.

The score used in the practice rounds is the **macro F1**, which we call the "balanced score". F1 combines two things: how many real cases of a category were caught, and how often a guess of that category was right. "Macro" means we average it over the 5 categories equally, so small categories like Fraud count as much as Payments. 1.0 would be perfect.

### The comparison

Each method was tuned by testing a few settings. The winner was chosen on the practice rounds, never on the final test.

| Model | Practice score (macro F1) | Final test accuracy |
|---|---|---|
| Always guess the biggest category (baseline) | 0.135 | 46.4% |
| Complement Naive Bayes | 0.940 | 95.3% |
| Linear SVM | 0.966 | 96.7% |
| Logistic Regression (chosen) | 0.966 | 97.3% |

"Accuracy" means the share of messages put in the right category.

The baseline shows why a simple accuracy number can fool you. Just guessing "Payments" every time gets 46.4% accuracy, but its balanced score is only 0.135, because it never gets any other category right.

### Why Logistic Regression won

- It had the best practice score. Logistic Regression and Linear SVM tie at 0.966 when rounded to 3 places, but Logistic Regression was slightly higher before rounding: 0.9663 vs 0.9655.
- It gives a percentage for how sure it is. We need that for the 60% manual-review rule and the 10% fraud rule.
- It is fast and simple. Training the whole thing takes about a minute on a laptop (61 seconds for this version).
- It is easy to explain: you can see which words pushed a message toward a category.

---

## 6. Results

All results are from the test set of **3,192 messages** the live model never saw.

### Overall

- **Accuracy: 97.3%.** That is **3,107 correct and 85 wrong**.
- **Balanced score (macro F1): 0.974**, where 1.0 would be perfect.

### Per category

Two plain definitions:

- **Caught % (recall):** out of every 100 real messages of this category, how many the system put in the right place. For fraud: out of every 100 real fraud messages, how many the system caught.
- **Right % (precision):** out of every 100 times the system said "this category", how many were really that category.

| Category | Caught % (recall) | Right % (precision) |
|---|---|---|
| Payments | 96.6% | 98.6% |
| Cards | 97.9% | 96.8% |
| Loans | 100% | 100% |
| Account issues | 98.8% | 95.6% |
| Fraud | 95.8% (230 of 240) | 93.9% |

Remember the loan caveat: the loan test messages come from templates, so 100% is optimistic.

### The confusion matrix

This table shows where every test message ended up. Each **row** is the real category. Each **column** is what the system guessed. Numbers on the diagonal (same row and column name) are correct. Everything else is a mix-up.

| Real \ Guessed | Payments | Cards | Loans | Account | Fraud |
|---|---|---|---|---|---|
| **Payments** | **1430** | 27 | 0 | 11 | 12 |
| **Cards** | 11 | **939** | 0 | 6 | 3 |
| **Loans** | 0 | 0 | **113** | 0 | 0 |
| **Account** | 3 | 2 | 0 | **395** | 0 |
| **Fraud** | 7 | 2 | 0 | 1 | **230** |

How to read one row: take the Fraud row. Of the real fraud messages, 230 were sent to Fraud correctly, 7 were sent to Payments, 2 to Cards and 1 to Account issues.

The biggest mix-ups:

- **Payments guessed as Cards (27).** Many payment questions likely mention a card, like "my card payment is pending", so the words overlap.
- **Payments guessed as Fraud (12)** and **Payments guessed as Account (11).** A payment the customer is confused about can look a lot like an unrecognised one.
- **Cards guessed as Payments (11).** The same overlap in the other direction.
- **Fraud guessed as Payments (7).** These are the most important misses, because a real fraud case went to a slower team. The fraud safety net and agents moving tickets are there to reduce this.

Loans are never confused with anything, which again reflects the clean template wording.

### Topic model

- **90.0%** of messages get exactly the right topic out of 83.
- The right topic is in its **top 3 guesses 96.7%** of the time.

### Release check

| Check | Minimum needed | Achieved | Result |
|---|---|---|---|
| Balanced score | at least 0.93 | 0.974 | Passed |
| Fraud caught | at least 90% | 95.8% | Passed |
| Topic accuracy | at least 80% | 90.0% | Passed |
| Compared with the live model | no drop of more than 0.01 | passed | Passed |

---

## 7. Worked examples

These were all checked on the live system.

### Example 1: Fraud caught by the safety net

**Message:** "My card 4539 1488 0343 6467 was skimmed at the ATM"

- The card number is hidden as [CARD].
- The model on its own said **Cards (100%)**. It saw "card" and "ATM" and did not understand that "skimmed" means theft.
- The fraud rule spotted "skimmed", a strong phrase, and sent it to the **Fraud & Security Team, urgent, 1 hour**.
- Topic: Lost or stolen card.

**Why it matters:** this shows both the weakness of a word-based model and why we added the safety net. Without it, a theft would wait 24 hours at Card Services.

### Example 2: A loan question

**Message:** "How much will the EMI be on a 5 lakh home loan over 10 years?"

- Category: **Loans, 99.9% sure.**
- Team: **Lending Team, 48 hours.**
- Topic: Loan repayment.

**Why it matters:** it shows the loan gap was filled, and the system understands loan wording such as "EMI" (monthly instalment).

### Example 3: The system is unsure

**Message:** "hello there"

- The system is only **56% sure**, with a best guess of Payments.
- That is below the 60% line, so it goes to **manual review**.

**Why it matters:** the system knows when it does not know. Instead of guessing wildly, it asks a person.

### Example 4: A sensitive case

**Message:** "My father passed away and I need to close his account"

- Category: **Account issues.**
- The bereavement rule raised the priority to **high**.

**Why it matters:** the business rules add human care that a pure "which team" decision would miss.

---

## 8. What the app does

### The screens

- **Live routing.** As you type a message, it is classified straight away. An animated diagram shows lines running from the message's words to the 5 teams, so you can see what pushed the decision. One click then creates the ticket.
- **Inbox.** The agents' work list, sorted by urgency and deadline. Agents can change a ticket's status, move it to another team, assign it to someone and add notes. Every change is recorded in a full history.
- **Batch routing.** Paste many messages, or upload a CSV file (a simple spreadsheet file) with up to 1,000 messages, and download the results.
- **Analytics.** Charts of tickets per day, open work per team, deadlines missed, how often agents corrected the model, and how sure the model was.
- **Model report.** The scores, the model comparison, the list of versions and the release check results.

The app has light and dark mode and works on phones.

**Demo data:** to fill the Inbox and Analytics screens, we created 606 sample tickets spread over 14 days, made from real test-set sentences. The timings and agent actions are simulated. Be clear about this if asked.

### The API

An API is a door that lets other computer systems talk to ours. Another bank system can send a message to it and get back the team, topic and priority. It can be protected with optional access keys and limits on how many requests per minute each user can send.

### Engineering quality

- **49 automated tests** check that each part works, for example that card numbers really are hidden.
- **Automatic checks on GitHub:** every time the code changes, GitHub Actions runs the tests automatically, so a broken change is noticed straight away.
- **Docker packaging:** the whole system is packed into one box that runs the same way on any computer, which makes it easy to set up at a bank.

---

## 9. Honest limitations

Say these openly. Judges respect honesty more than perfection.

- **Loan data is generated from templates, not real customers.** The loan score is optimistic.
- **English only.**
- **One main category per message.** If a message mixes two problems, a second category is shown, but the ticket goes to one team.
- **The word-based model doesn't understand meaning.** On its own it missed "skimmed", "cloned" and "scam". The fraud rule now catches these, but a list of phrases can never cover every way of describing fraud. A smarter model is the real fix (phase 2).
- **Demo tickets are simulated** for timings and agent actions.

---

## 10. Phase 2 plan

These 6 tasks are the remaining 30% of the project.

| # | Task | Why it matters in plain words | Effort |
|---|---|---|---|
| 1 | Smarter language model (fine-tuned DistilBERT), competing with the current one through the same release check | It understands meaning, not just words, so it could catch "my card was cloned" without needing a rule. It only goes live if it beats the current model. | 1–2 days |
| 2 | Drift monitoring | Customer language changes over time (new scams, new products). This warns us when the system starts seeing messages unlike what it learned. | 1 day |
| 3 | Instant alerts for urgent tickets (Slack or email) | A fraud ticket with a 1-hour deadline should not wait for someone to open the inbox. | Half a day |
| 4 | Production database (Postgres) with safe upgrades of its structure | A stronger place to store tickets that a real bank can rely on, and that can be changed safely later. | Half a day |
| 5 | Load test | Measures how many messages per second it can handle, so we know if it can cope with a busy day. | Half a day |
| 6 | Project report notebook with error analysis | A written study of the 85 mistakes: what they have in common and how to fix them. | 1 day |

---

## 11. Likely judge questions

**1. Why not just use ChatGPT?**
Customer messages contain private details, and sending them to an outside service is a privacy risk for a bank. Our system can run on the bank's own computers (it is packaged with Docker), it trains in about a minute on a laptop, and we can explain every decision and test every new version with a release check. A smarter language model is in our phase 2 plan, and it must beat the current model through the same release check before it is used.

**2. Is 97.3% good enough for a bank?**
97.3% means 3,107 of 3,192 test messages went to the right team and 85 did not. But the system is not working alone. When it is less than 60% sure, a person checks. The fraud safety net catches strong fraud phrases whatever the model says. And agents can move a wrong ticket in one click, which also teaches the next version. It is a first sorter that saves staff time, not the final decision on a customer's money.

**3. Your loan data is fake. Isn't that cheating?**
Banking77 has no loan questions, and the problem statement asks for loans, so we had to fill the gap. We wrote 60 templates across 6 loan topics and kept the test templates separate from the training ones, so the test only has wording the system never saw. But we openly say the loan messages are cleaner than real ones, so the 100% loan score is optimistic. With real bank data, we would replace them.

**4. What happens when the model is unsure?**
If it is less than 60% sure, the message goes to manual review (General Support) with a 24-hour deadline, and a person decides. For example, "hello there" got only 56% and went to review.

**5. How do you protect customer privacy?**
Card numbers, account numbers, IBANs, sort codes, emails and phone numbers are replaced with placeholders like [CARD] before anything is stored or read by the model. The system can also run on the bank's own computers, so messages do not need to go to an outside service. The API can be locked with access keys.

**6. How would this get better over time?**
When agents move a ticket to the correct team, that correction is saved and used to train the next version. Our current training data already includes 1 such correction. Every new version must pass the release check, so a new version cannot go live if it is noticeably worse than the current one (no drop of more than 0.01). Phase 2 adds drift monitoring to warn us when customer language changes.

**7. Why did you choose this dataset?**
Banking77 is real customer wording with typos and chat style, it is all about banking, it is free under the CC BY 4.0 licence, it is already labelled, and it is widely used for exactly this task. That means anyone can check our results.

**8. What was the hardest part?**
Two things. First, the loan gap: we had to create loan questions and keep training and test wording apart so the test stayed fair. Second, fraud: the model on its own missed words like "skimmed", "cloned" and "scam" because it doesn't understand meaning. We added the two-level fraud safety net so strong phrases always go to Fraud, while weak words like "fraud" only count if the model also gives fraud at least 10%.

**9. What if a real fraud message is missed?**
On the test, the system caught 95.8% of fraud messages, 230 of 240. The release check requires at least 90%, so a new version cannot go live if fraud catching drops below that. The safety net catches strong phrases, and agents can move a ticket to Fraud. A smarter model in phase 2 is the bigger fix.

**10. How do you know you didn't cheat on the test?**
We removed any sentence that appeared in both training and test sets. We chose the model only on practice rounds inside the training data, never on the test. The test was used only to report the final score.

**11. Why Logistic Regression and not something fancier?**
It had the best practice score (0.9663 vs 0.9655 for Linear SVM before rounding), the best final accuracy (97.3%), it tells us how sure it is (which our 60% and 10% rules need), it trains in about a minute on a laptop, and its decisions are easy to explain.

**12. Why do you need a topic model as well as a category model?**
The category picks the team. The topic, out of 83, tells the agent exactly what the problem is, such as "lost or stolen card", so they can start helping straight away. It gets the exact topic right 90.0% of the time, and the right topic is in its top 3 guesses 96.7% of the time.

**13. Can the bank change the rules without a programmer retraining the model?**
Yes. The rules (the 60% review line, the fraud phrases, the priority boosts) live in a settings file. They can be edited without retraining.

**14. Does it handle messages about two things at once?**
Partly. It picks one main category for the ticket, and shows a second one for mixed messages so the agent can see it. Proper multi-team handling is a known limitation.

**15. Is the inbox data real?**
No. The 606 demo tickets over 14 days are made from real test-set sentences, but the timings and agent actions are simulated, so the screens have something to show.

**16. Does it work in other languages?**
No, it is English only at the moment.

**17. How do you know the code works?**
There are 49 automated tests, and GitHub Actions runs them automatically on every change. The system is also packaged with Docker so it runs the same way everywhere.

---

## 12. Cheat sheet: 10 numbers to remember

| Number | What it means |
|---|---|
| **97.3%** | Category accuracy on the test: 3,107 correct, 85 wrong. |
| **3,192** | Test messages the system never saw while learning. |
| **10,519** | Training messages: 9,974 Banking77 + 544 loan + 1 agent correction. |
| **0.974** | Balanced score (macro F1) across the 5 categories; 1.0 is perfect. |
| **95.8%** | Fraud caught: 230 of 240 real fraud test messages. |
| **90.0% / 96.7%** | Topic model: exactly right / right topic in its top 3 guesses. |
| **83** | Topics the system knows: 77 from Banking77 + 6 loan topics. |
| **60** | Loan templates we wrote to fill the gap (Banking77 has no loans). |
| **60%** | Below this level of sureness, a person checks the message. |
| **1 hour** | Response deadline for the Fraud & Security Team (urgent). |

Also worth knowing: topic split 37 / 24 / 10 / 6 (Payments / Cards / Account / Fraud); deadlines 1 h / 8 h / 24 h / 24 h / 48 h; weak fraud words need at least 10% from the model; 49 automated tests; 606 demo tickets over 14 days; release check needs balanced score at least 0.93, fraud caught at least 90%, topic accuracy at least 80%.
