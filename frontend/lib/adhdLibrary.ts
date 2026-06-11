// Curated, hand-built library of ADHD-themed children's-book ideas.
//
// The unit of choice is a COHERENT STORY CONCEPT: one protagonist with a
// consistent name, pronouns, and arc threaded through the title, characters,
// setting, and description. The create-book form picks/shuffles whole concepts
// so the fields always make sense together — you can't accidentally pair one
// child's title with another child's description. Every field stays freely
// editable afterward, so there's still room to tweak.
//
// THEME is intentionally fixed — every book in this pipeline is about the ADHD
// experience — so it is not an editable field. See LOCKED_THEME below.

export const LOCKED_THEME = "ADHD";

export interface AdhdConcept {
  id: string;
  title: string;
  characters: string;
  setting: string;
  description: string;
}

// Each concept is internally consistent: the name and pronouns in the title,
// characters, and description all refer to the same child.
export const ADHD_CONCEPTS: AdhdConcept[] = [
  {
    id: "max",
    title: "Max and the Loud Quiet",
    characters: "Max (8, a boy whose brain never stops zooming), Nia (his calm, patient best friend)",
    setting: "A busy, colorful classroom with a quiet, cozy reading nook in the corner",
    description:
      "Max's thoughts race like little race cars and sitting still feels impossible — until he and his friend Nia find a cozy quiet corner and his own way to focus. A warm, funny story that reassures children a fast brain is a gift, not a flaw.",
  },
  {
    id: "zoe",
    title: "Zoe's Zoomy Brain",
    characters: "Zoe (7, a girl with a hundred ideas a minute), Grandpa Theo (who listens to every one)",
    setting: "A grandparent's slow, sunny garden where time stretches out",
    description:
      "Zoe has a hundred ideas a minute and nowhere to put them all, until a patient afternoon in Grandpa Theo's garden helps her catch one idea at a time. A gentle story about a racing mind and the relief of being truly listened to.",
  },
  {
    id: "sam",
    title: "Sam Can't Sit Still (and That's Okay)",
    characters: "Sam (6, who can't sit still in class), Ms. Okafor (the teacher who gets it)",
    setting: "A bright playground at recess — loud, fast, and wonderful",
    description:
      "Sam simply cannot sit still, until Ms. Okafor shows the class that wiggles and movement can actually help a body learn. A reassuring story about fidgety bodies and making room for every kind of learner.",
  },
  {
    id: "pippa",
    title: "Pippa and the Hundred Ideas",
    characters: "Pippa (8, a daydreamer who forgets her shoes), Bolt (her scruffy reminder dog)",
    setting: "A morning routine that somehow always runs five minutes late",
    description:
      "Pippa daydreams so wonderfully that she forgets her shoes, her lunch, and the time — so she and her scruffy dog Bolt invent a playful reminder system of their own. A story that needing a little help isn't failing, and that imagination is a strength.",
  },
  {
    id: "leo",
    title: "Leo's Lightning Mind",
    characters: "Leo (9, lightning-fast and big-hearted), Coach Park (who sees his spark)",
    setting: "A soccer field where everything moves fast and feelings move faster",
    description:
      "Leo's mind moves at lightning speed, and sometimes he worries he's 'too much' — until Coach Park helps him see that his energy and big heart are exactly the right amount. About self-worth and finding people who see your spark.",
  },
  {
    id: "maya",
    title: "When Maya's Feelings Got Too Big",
    characters: "Maya (7, whose feelings come in tidal waves), Auntie Rosa (her safe harbor)",
    setting: "A crowded birthday party that starts to feel like a little too much",
    description:
      "When a birthday party gets too loud and Maya's feelings rise like tidal waves, Auntie Rosa helps her find a quiet corner, a slow breath, and the words for what she feels. A gentle story about big emotions and emotional regulation.",
  },
  {
    id: "ravi",
    title: "Ravi and the Reminder Robot",
    characters: "Ravi (8, an inventor who loses track of time), Ena (his quietly clever little sister)",
    setting: "A science fair the night before the big day",
    description:
      "A forgetful young inventor races to finish his science-fair project on time and learns, with his sister Ena's help, that asking for support and breaking a big task into small steps can save the day. About time-blindness and teamwork.",
  },
  {
    id: "bea",
    title: "Bea's Busy, Bouncy Day",
    characters: "Bea (6, a bouncy, joyful tornado), Pepe (her wise pet tortoise)",
    setting: "A kitchen-table art studio buzzing with paint, glitter, and chatter",
    description:
      "Bea is a bouncy, joyful tornado who starts a dozen glittery projects at once, until her slow, wise tortoise Pepe shows her the fun of finishing just one. A bright story about boundless energy and gentle focus.",
  },
  {
    id: "finn",
    title: "Finn and the Dinosaur Deep-Dive",
    characters: "Finn (7, who hyperfocuses on dinosaurs), Dad (who learns to really listen)",
    setting: "A rainy-day living room transformed into a blanket-fort headquarters",
    description:
      "Finn knows everything about dinosaurs and nothing about stopping — until Dad turns the living room into a blanket-fort HQ and learns to really listen. A tender story that deep focus is a superpower worth sharing.",
  },
  {
    id: "ada",
    title: "The Day My Thoughts Went Everywhere",
    characters: "Ada (9, clever but easily overwhelmed), Coco (her steady, purring cat)",
    setting: "A library with a secret, soft-lit corner just for one",
    description:
      "Ada is clever, but on busy days her thoughts scatter everywhere at once — until a soft-lit library corner and her steady cat Coco help her gather them back. About overwhelm, self-soothing, and finding your quiet.",
  },
  {
    id: "theo",
    title: "The Superpower Nobody Saw",
    characters: "Theo (8, who blurts before he thinks), Jada (the friend who forgives)",
    setting: "A noisy school cafeteria and a calm treehouse hideaway after the bell",
    description:
      "Theo blurts out something that hurts his friend Jada, then learns to pause, repair the friendship, and forgive himself. A warm story about impulsivity, empathy, and the quiet superpower of making things right.",
  },
  {
    id: "ollie",
    title: "Ollie Forgets (but Never the Important Things)",
    characters: "Ollie (6, who forgets homework but never a kindness), Mrs. Lee (his teacher)",
    setting: "A cluttered bedroom full of half-finished, wonderful projects",
    description:
      "Ollie forgets his homework, his coat, and his library books — but never a friend's bad day. With Mrs. Lee's help he builds little systems for the forgettable stuff, and learns his big heart was never the problem.",
  },
];

/** Pick a uniformly random element. */
export function pickRandom<T>(items: T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

/** A fresh, coherent ADHD story concept to prefill the form. */
export function randomAdhdConcept(): AdhdConcept {
  return pickRandom(ADHD_CONCEPTS);
}
