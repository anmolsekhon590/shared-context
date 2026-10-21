# No Memory, No Harness: Why the Database Is the Last Line of Defense — Kay Malcolm, Oracle

> Transcript extracted from https://ai.engineer/talks/jA_x7F8caHI-no-memory-no-harness-why-database-is (YouTube: https://www.youtube.com/watch?v=jA_x7F8caHI)

**Speaker:** Kay Malcolm (Oracle)  
**Duration:** 21.6 min · **Segments:** 461 · **Words:** ~3054  
**Extracted:** 2026-10-20 (source checksum `df9358fa334087a8`)

## Summary (publisher-provided)

Kay Malcolm describes how faster AI-assisted coding left her distributed team without shared decision context. She presents memory as an essential component of an agent harness and argues for consolidating different memory representations in a database. She describes a team memory broker using Oracle's agent memory SDK to share context associated with forks, branches, and commits while developers retain control.

## Key points (publisher-provided)

- Malcolm reports that AI accelerated individual work without improving team productivity: code handoffs omitted context, and Git recorded code rather than human intent.
- She describes the model as a brain, the harness as its body, and memory as the nervous system carrying context. Her harness discussion includes tools, context, retrieval, security, and guardrails.
- She distinguishes five memory types: short-term session memory, long-term memory across sessions, episodic memory of prior interactions, procedural memory of tools and steps, and semantic memory.
- A database administration anecdote and a four-volunteer exercise illustrate her argument that separate specialized stores add operational work and complicate identifying a single source of truth. She advocates storing multiple data representations together in Oracle AI Database.
- She describes a memory broker that shares team context and associates it with forks, branches, and commits. The example uses Oracle's agent memory SDK and an autonomous database, with a choice of LLM or a local model.

## Editor's notes — why this talk matters for shared-context

This is a vendor talk (Oracle), but the *diagnosis* matches our thesis exactly; the prescription is
"buy Oracle." We're building the open-source, DB-agnostic version of the same insight.

**The motivating scenario (better than any abstract framing):** a team split between EMEA and the US.
At 4am the Netherlands team checks in code, but not the Codex context that produced it. The US team
wakes up to a diff with no rationale, re-derives everything, and burns tokens doing it.

**Key quotes (verbatim from ASR):**

> "Git records the code and not human intent."

> "AI makes individuals faster. Shared memory ... makes teams faster."

> "Memory is the thing that becomes non-negotiable in an agent's harness."

> Harrison Chase, quoted: "Your harness, your memory. And if you don't own your harness, you don't own your memory."

> On Claude/memory.md-style memory: "it's kind of like file system memory and it works with one, but ... when you scale past one ... it creates a problem."

**Harness anatomy she proposes:** model = brain; harness = body; memory = central nervous system carrying
context. Harness components: tools, context, memory, retrieval, security, guardrails.

**Five memory types:** short-term (session), long-term (across sessions), episodic ("what happened last
 time I interacted with X"), procedural (tools, steps taken), semantic (enterprise facts).

**The memory broker:** a service ("Polly") that captures context automatically, records *which fork,
branch, and commit* each piece of context belonged to, and shares it across the team while
"developers remain in control." Stored in a single database (Oracle AI Database 26ai) precisely so the
agent doesn't have to reconcile a relational store + document store + graph store + vector store and
guess which is the source of truth (she demonstrates this failure with 4 volunteers and the sentence
"the cow jumped over the moon").

**ASR corrections:** `Codeex` → Codex · `cloud code`/`claude code` → Claude Code · `AMIA` → EMEA ·
`Sarbain Oxley` → Sarbanes-Oxley · `roofcar`/`rockar` → rockstar · `Albundy` → Al Bundy ·
`Py`/`PY`/`Polly` → same memory broker (spelling uncertain) · `Reddus` → Redis · `tenency` → tenancy ·
`unstructured JSON database` → document/JSON store. Transcript is otherwise verbatim, unedited.

## Transcript

**0:12** Everyone, are we having fun?
**0:15** >> Oh, you've got to give me way more than
**0:18** that. So, let me tell you, um, my name
**0:20** is Kay Malcolm. I am a retired hiphop
**0:23** instructor. So, if I don't get more
**0:25** energy than that, we will start. We'll
**0:28** start. Are you having fun? [cheering]
**0:32** >> Okay. All right. So, here's what we're
**0:34** going to talk about today. Now, you guys
**0:36** have heard a lot about two letters. Does
**0:39** anyone want to guess what those two
**0:41** letters are that I'm going to talk about
**0:42** today?
**0:46** >> Data. That was pretty good. DB. I'm
**0:48** going to talk about AI, but I'm
**0:50** specifically going to talk about agent
**0:53** harnesses. But before I do that, I want
**0:56** to introduce you all to a few people. Is
**0:57** that okay?
**0:59** Yes or yes. Is that okay?
**1:02** >> I gave choices. Yes. Anyway. All right.
**1:05** Okay. All right. This is my team.
**1:09** I run an outbound database product
**1:12** management team at Oracle. I've been at
**1:14** Oracle a really long time, 20 years.
**1:18** Funny story, I started when I was 12.
**1:20** So, don't do the math and don't start
**1:22** start adding in your head. Um, and we've
**1:25** got a problem. That problem is I've got
**1:29** one group
**1:31** that does platform development and then
**1:34** I have another group that does content
**1:36** development for live labs, a platform
**1:38** that I wrote myself. So yeah, I'm an
**1:41** engineer but I'm kind of a developer
**1:43** poser too. And then I've got another
**1:45** group who does QA
**1:48** and then I have another group who does
**1:49** my front-end development
**1:52** with AI. Here's what I found out as a
**1:56** leader. Because in the token maxing era
**2:00** of 2025, because you know, we're not
**2:02** token maxing anymore, right?
**2:05** We are responsible AI now. But in the
**2:08** token maxing era, the thing that I found
**2:10** out was while AI was making the
**2:14** individuals on my team faster, there was
**2:18** another problem it was creating.
**2:23** It wasn't making my team more
**2:26** productive.
**2:28** And the reason was when one team from
**2:32** the Netherlands checked in code at my
**2:35** 4:00 a.m. in the morning because I've
**2:37** got half of my team that's in AMIA and I
**2:39** have half of my team who that are here
**2:41** in the United States. They checked in
**2:44** the code but they didn't check in their
**2:47** context from Codeex. We use Codeex at
**2:50** Oracle.
**2:51** So then when the US team woke up,
**2:56** they got the code but no information
**2:59** about the context. So we used AI to
**3:03** solve a problem that AI created. And
**3:07** here's what we did. Oh well, let me talk
**3:09** about this first. So some of the issues,
**3:12** the context, like I said, wasn't shared.
**3:15** GitHub wasn't tracking that. I had
**3:19** repositories that were diverging and I
**3:21** was asking the managers who work for me,
**3:24** what's happening to your teams? Why why
**3:27** are we not going faster? We're spending
**3:30** all of this money on tokens. We're
**3:31** spending all this money on AI, yet
**3:33** something is missing because we're still
**3:36** spending time doing testing and
**3:39** validation. So our netn net wasn't
**3:41** really wasn't really working for us
**3:45** because git records the code and not
**3:47** human intent.
**3:49** So it's a problem
**3:52** and
**3:53** even though code creation
**3:58** was no longer our problem
**4:00** still had a bottleneck.
**4:03** We needed a collaboration layer. Now, I
**4:07** do have members of my team in the
**4:09** audience, so don't judge me, and you
**4:12** know who you are. I'm not saying that
**4:14** you all didn't collaborate. But now,
**4:18** we've got a new team member, and that
**4:20** new team member is AI.
**4:23** So,
**4:25** we needed to figure out how to track our
**4:27** progress in our next steps. how to
**4:31** rationalize decisions
**4:33** that the
**4:36** agent was making.
**4:39** We needed to figure out how to resolve
**4:43** questions in conflicts.
**4:45** Okay,
**4:48** hold my problem. Will you all hold my
**4:50** problem for me right here? We're going
**4:51** to just tuck that in a little box. Let
**4:54** me define what a enterprise agent
**4:58** actually is. Now, most people think that
**5:00** an enterprise agent is the model and
**5:04** workflow. How many people agree with me?
**5:08** Man, this tough crowd you. Okay, one
**5:11** person. Okay, the rest of you think it's
**5:14** a little bit more. Okay, let's see what
**5:18** could it be that a real enterprise agent
**5:24** has tools.
**5:26** Tools are how it does things.
**5:30** Context.
**5:33** The context. That's a context window.
**5:35** That's what's in the actual prompt.
**5:39** Memory.
**5:40** Huh?
**5:43** And if you're thinking, "But wait, K,
**5:46** memory, you just said that the model is
**5:48** kind of like the brain of the
**5:50** operation." Hold tight. We're going to
**5:52** talk a little bit more about memory
**5:56** retrieval because you don't want to get
**5:58** everything back. So that's being able to
**6:00** to retrieve the right information back.
**6:04** And then I know that there are a lot of
**6:06** developers here and you all don't care
**6:08** about security.
**6:11** I care about security because I work for
**6:14** the most secure database company and I
**6:17** used to work for um agency that has no
**6:21** name. But guard rails is also important.
**6:25** This is the harness. I speak in
**6:28** analogies and I and I speak in stories
**6:31** because if I tell you this and Marvel,
**6:35** you know exactly what I'm talking about.
**6:38** So the agent, think of it as the model,
**6:42** little brain floating a in a glass jar
**6:46** plus this harness. This harness is the
**6:50** body.
**6:52** So it's how the agent can actually do
**6:55** things and get things done. That memory,
**7:00** that's the part of the central nervous
**7:03** system. And you remember the central
**7:04** nervous system connects the brain to the
**7:07** rest of the body, legs, arms. That's the
**7:11** part of the central nervous system that
**7:14** carries context. So you remember my
**7:17** problem with Git.
**7:20** What I needed was memory. Okay, so there
**7:24** are a number of memory types. I chose
**7:27** five, the five most common ones that
**7:29** people talk about and these are the ones
**7:30** that I want you to remember. The first
**7:32** one is short-term memory. That's the
**7:34** session, right? And so if you're storing
**7:38** memory of an AI uh process, that is the
**7:42** short-term memory is if you're with
**7:45** chat, cloud code, right? Codeex, pick
**7:48** your poison. The long-term memory is
**7:51** what persists across sessions.
**7:55** Episodic memory. Hm.
**7:58** What happened the last time
**8:03** I interacted with fill in the blank?
**8:06** That's your episodic memory. Procedural
**8:09** memory
**8:11** tools, steps that were taken.
**8:15** And then finally, semantic memory. And
**8:18** semantic memory because we're talking
**8:19** enterprise agents. We're not talking the
**8:23** agent that I built, Sasha Fierce,
**8:25** because remember I told you guys that I
**8:26** was a I'm a a dancer. So, of course, my
**8:30** my chief of staff is going to be called
**8:32** Sasha Fierce because that was Beyonce.
**8:34** Any Beyonce fans?
**8:37** Okay, I'm sorry. All right, we got to
**8:39** focus. Okay, so these are the memory
**8:42** types. Now, when you're defining this
**8:45** real enterprise agent in this memory,
**8:50** there's something you need to consider
**8:51** where to store it. And so, I'm going to
**8:53** tell you guys a story. But when I tell
**8:56** you the story, you have to promise me
**8:58** that you're not going to judge me. Do
**9:00** you promise?
**9:06** Do you promise
**9:08** >> you're not recording me, right? Because
**9:10** this doesn't paint me in a good light.
**9:12** Okay. All right. The world of data was
**9:14** one simple. I've been at Oracle a long
**9:16** time, but I came from a customer. That
**9:18** customer's name was Southern Company. It
**9:19** was a power company. I'm based out of
**9:21** Atlanta. And I was hired at Southern
**9:24** Company because I was a rockar
**9:27** performance tuner. You had a SQL query.
**9:29** I mean, I'm dating myself, but whatever.
**9:31** You had a SQL query. I knew all of the
**9:33** innit.org parameters. Even the ones when
**9:35** you called support and they said, "Don't
**9:37** remember these. Don't write them down."
**9:38** I wrote them down in my little notebook.
**9:40** I could tune a query within one inch of
**9:42** its life. Then one of you came to my
**9:47** desk because I mean the world the world
**9:49** was rows and columns. It was a great
**9:51** time back in my Albundy days um and said
**9:56** hey I need to store data unstructured.
**10:01** Why I need to do that?
**10:04** And so me being K the the diligent DBA,
**10:08** I was like, "Let me figure it out and
**10:11** get back to you."
**10:14** Did I get back to him?
**10:16** I didn't get back to him. Now, the thing
**10:19** you have to know about Southern Company
**10:21** was for every database system that a DBA
**10:24** managed, I had to attend two meetings.
**10:26** Today, when I hear Sarbain Oxley, I
**10:29** still throw up a little bit in the back
**10:30** of my throat. So I had to attend a
**10:32** security meeting and a patching meeting
**10:34** every week. Never failed. Now because
**10:38** this developer installed a database that
**10:42** was specialized for unstructured. Okay,
**10:45** there are really smart people in the
**10:46** room. How many meetings am I going to
**10:48** now?
**10:54** Four. Okay, I'm a little annoyed, but
**10:56** I'm like, okay, we can we can we can do
**10:59** this. Then they said, "Okay, since
**11:01** you're such a good tuner,
**11:03** I need you to figure out this
**11:05** relationship." Now, the way that
**11:07** Southern Company worked, there was this
**11:09** people could die application, um, and it
**11:12** was a it was like a Nokia phone that
**11:16** people who were climbing the towers,
**11:18** right? So, you guys have have been in a
**11:20** storm and the power goes out, right? And
**11:23** then you're pretty sure that within
**11:25** maybe an hour or two the power will go
**11:27** on. Well, that system that would tell
**11:31** the people who were climbing those trees
**11:32** and risking their lives to turn the
**11:34** power back on sometimes would have false
**11:37** positives or false negatives. So, they
**11:39** wanted to look at all of the other um uh
**11:44** polls in the area
**11:46** to try to get away from the false
**11:48** positive or the false negative. And so I
**11:50** did that in a SQL query and it was it
**11:53** was amazing. It was a five nested union
**11:57** all statement. It was some of my best
**11:59** work. Now it might have taken like 20
**12:01** minutes to work but it was like a
**12:03** predecessor to graph.
**12:06** Yeah, they they install Neo4j.
**12:10** So now how many meetings am I going to?
**12:13** Six. That's a problem.
**12:17** So I um Oh, let me I got ahead of
**12:19** myself. So you know what I did? I quit.
**12:23** I left and I came to Oracle because I
**12:24** was like this is a problem and maybe I
**12:26** can go to Oracle to help solve it. So
**12:27** then Joe Mundy called me and he said hey
**12:30** um we are installing Reddus. Oracle is
**12:34** late to the game. We've got a vector
**12:36** database.
**12:38** Okay.
**12:40** But here's your problem, Joe.
**12:45** Agents now need access to all of this
**12:48** data. So if data is in an Oracle
**12:51** database, if then it's also in an
**12:53** unstructured JSON database, if it's in a
**12:55** graph database and it's in a vector
**12:58** database, where is your single source of
**13:01** the truth?
**13:03** The agent has to figure that out.
**13:05** Sometimes it'll get it right.
**13:08** Most times it'll get it wrong and it's
**13:10** going to burn up a whole bunch of
**13:11** tokens. And so now if you want to store
**13:15** your memory somewhere, you can store it
**13:17** in a file system.
**13:20** You can store it in
**13:23** clawed or chatgpt because we all know
**13:25** about the memory.md file.
**13:29** But that's going to be a problem. Now I
**13:31** want to illustrate this. I need four
**13:32** volunteers. I can see you raise your
**13:34** hand. One, two. Okay, I can't. Maybe I
**13:38** can. Three.
**13:40** I need a fourth. Ah, fourth in the back.
**13:43** Okay. Fourth in the back. You are going
**13:45** to be our old reliable. You're going to
**13:47** be a relational database. Yes or yes.
**13:50** You got your So, you have your
**13:51** assignment. Okay. And then there was
**13:53** someone here. You're going to be my
**13:56** unstructured database. Okay. And then
**13:58** where was my other? Ah, very good.
**14:00** You're going to be my graph database.
**14:02** You good? Relationship guy. You look
**14:04** like a relationship guy. All right. Very
**14:06** good. Fourth. Where was my fourth?
**14:09** Was it you? Yes. Yeah. You are my vector
**14:14** database. Okay. Now, everybody be
**14:18** really, really quiet.
**14:20** For my four volunteers, I need you all.
**14:24** I'm going to say something to you. And I
**14:28** need you all to decide how you're going
**14:30** to store it and who's going to have the
**14:32** single source of the truth. You can't
**14:34** get up from your seats and you have to
**14:36** whisper because if you talk loud that's
**14:38** 5x the tokens for you. Yes.
**14:41** Okay. Are we ready? All right.
**14:44** The cow jumped over the moon.
**14:49** Go.
**14:53** Doesn't really work, does it? That's a
**14:56** problem. Okay,
**14:59** Oracle. And if you don't forget one, if
**15:02** you forget everything I say and you
**15:04** remember one thing,
**15:06** Oracle is not the Oracle that you think
**15:09** that is why I am here today. How many of
**15:12** you knew that Oracle could natively in
**15:16** the same table down to the same
**15:18** partition store JSON graph vector my
**15:23** vector friend over there my JSON friend
**15:26** spatial
**15:28** you want your memory to be immutable
**15:30** blockchain in the same database raise
**15:33** your hand yeah
**15:36** we have a marketing problem
**15:39** so any data type can be stored in a 26AI
**15:44** database any workload anywhere AWS GCP
**15:49** Azure OCI on prem choice and flexibility
**15:54** so now when we take this and we talk
**15:56** about the agent I want to be able to
**15:58** store my long-term and procedural memory
**16:00** in relational on in JSON I want to store
**16:03** my short-term and my long-term memory
**16:05** graph I want to store procedural because
**16:07** procedural that's how I figure out the
**16:09** relationships right the steps
**16:11** my episodic and semantic memory. I need
**16:14** to do some vector and then store it also
**16:17** as text. Now, if I have four different
**16:22** databases, you all saw they can't talk
**16:24** to each other. It's going to be a
**16:26** problem. And so, what I'm saying to you
**16:29** today is the Oracle AI database is the
**16:33** best place to store this agent memory
**16:36** that's going to power your harness.
**16:38** Remember your harness is your body
**16:40** [music] and that memory is your central
**16:42** nervous system. Okay, back to PY. So the
**16:47** problem that I had, we solved it with a
**16:49** memory broker named Py. We used agent
**16:53** memory. We got out of that automatic
**16:56** continuity.
**16:58** So with my team, they were able to share
**17:01** not just their code, but PY also kept
**17:05** track of the context. So if one context
**17:09** window was had procedural memory,
**17:12** episodic memory, information about the
**17:14** long-term memory, that was then shared
**17:17** with the other folks on the team. You
**17:20** could call them agents, if you will.
**17:21** They're just human agents shared across
**17:24** forks.
**17:26** The developers on the team remained in
**17:28** control while Polly was able to create
**17:34** the context, figure out which fork and
**17:37** branch it belonged to and which commit
**17:40** it belonged to. Now this is a very
**17:42** simplistic example but when you take
**17:45** this to the enterprise here's what
**17:47** happens.
**17:49** Memory is the thing that becomes
**17:51** non-negotiable in an agent's harness.
**17:54** Now these are three papers that that I
**17:56** read um on the airplane. This first one
**18:00** is from open AI and it's about its
**18:01** in-house data agent and the thing that
**18:03** it says is it is saying that its
**18:07** in-house data agent actually needs
**18:10** memory. Memory was crucially important
**18:13** to ensure that its agent was able to
**18:16** filter correctly instead of trying to
**18:18** string match.
**18:20** Harrison Chase said, "Your harness, your
**18:23** memory. And if you don't own your
**18:24** harness, you don't own your memory."
**18:26** Which is key. And then I'm sure you all
**18:29** are wondering, "Well, Claude has memory.
**18:31** Why can't I use that?" Well, it's kind
**18:32** of like file system memory and it works
**18:35** with one, but just like in my example,
**18:38** when you scale past one, and you're
**18:41** going to scale past one in the
**18:43** enterprise, it creates a problem. So
**18:46** Oracle has a Oracle agent memory pap
**18:50** package. PIP install Oracle agent
**18:53** memory. You get access to it. And this
**18:56** memory is this SDK that we have is the
**19:01** thing that will hold your live
**19:02** conversations, your memories, your facts
**19:05** and figure out what is worth keeping. So
**19:08** if we look at Py now, Kevin
**19:12** can share his context with Py, our
**19:15** memory broker. We use the Oracle agent
**19:17** memory SDK. It's stored in an Oracle
**19:20** autonomous database.
**19:23** We can use the LLM of our choice or we
**19:25** can use a local model through the Oracle
**19:27** private AI services container.
**19:31** And then Linda, who's actually sitting
**19:33** right here, can interact and work with
**19:36** Kevin, no issues.
**19:38** So yes, AI makes individuals faster.
**19:42** Shared memory on an Oracle AI database
**19:44** makes teams faster. So I don't want you
**19:47** all to compromise. In the age of AI,
**19:50** what 26AI does is you can choose
**19:55** and pick what's best for agent memory
**19:58** file system stored in a database file
**20:00** system or in the database. If you need
**20:03** to do data modeling, you've got JSON,
**20:05** you've got relational. We've got choice.
**20:10** Okay, I've got some goodies for you. The
**20:12** Oracle AI developer hub. That's where
**20:15** you can guys you guys can get coding
**20:16** materials, the applications, what I
**20:18** talked about today. Livelabs.oracle.com.
**20:21** If you've done any of our workshops
**20:23** today, that happens to be something that
**20:25** I wrote myself about six years ago and
**20:27** 40 million users um ago. Spend my OCI
**20:31** tenency money.
**20:33** kick the tires on any Oracle technology
**20:36** um for six hours, 12 hours, however long
**20:39** you need. Um and then I'm giving you all
**20:42** all a Mac Mini. No, I'm just kidding.
**20:45** I'm giving you an OCI Mini. So, I don't
**20:47** know if you knew, but there is an always
**20:49** free OCI. It is the most generous of any
**20:52** of the hyperscalers where you can get a
**20:54** free Oracle database, free compute, you
**20:57** can send 3,000 emails a month, 200 gig
**21:00** in storage, and if you click on that,
**21:03** you can get access to it. Or just search
**21:06** Google for Oracle Cloud, always free.
**21:10** Connect with me. If you build something,
**21:13** will you all message me and let me know?
**21:15** Yes or yes?
**21:18** >> Thank you.
**21:34** >> [music]
