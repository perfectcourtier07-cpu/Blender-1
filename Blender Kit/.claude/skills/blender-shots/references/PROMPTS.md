# Blender Kit: prompts

Copy, change the words in CAPS, paste into Claude in your Blender Kit folder. Claude renders into `shots/<name>/` and tells you the file. Every render uses 1 sample on purpose (fast, and it looks fine on a dark stage); don't ask Claude to raise it, ask for better light instead.

## Setup

> Run the Blender setup.

> Continue setup.   (after you installed Blender yourself, or after a restart)

> Install the Blender skill from C:\Users\YOU\Downloads\Blender-Kit-2-Blender-Skill.zip

> Check my Blender setup and tell me how fast this computer is for renders.

## Your first shot

> Make a 5-second 3D title that says MY FIRST 10K, with 10K in gold. Show me stills first.

> Just render it.   (when the stills look right)

## The shots from the video

Every shot in the showreel is in the download as an example. Ask for one by name and give your own data:

> Make me the 3D reconstruction shot from the video: an airplane cabin, row 22 lit, a family of three in red, the callout "ROW 22 · 36,000 FT · 189 PASSENGERS", the cabin lights go out at 3 seconds. 8 seconds.

> Make the reconstruction look for a train carriage instead of a plane, 4 seats across, car 5 lit, callout "CAR 5 · 07:42".

> Make me the cinematic diorama shot from the video for K2: 8,611 m, camps at "CAMP III · 7,350 M" and "SUMMIT · 8,611 M", title "K2" with the line "8,611 M · THE SAVAGE MOUNTAIN". 7 seconds.

> Make the diorama look but for a ship on dark water instead of a mountain, with a route line and one label.

> Make me the 2D cartoon shot from the video: a king and a goat on a hill, the king talks, captions "IN 1348" / "A KING" / "TAXED HIS OWN GOAT." / "THE GOAT LEFT." 7 seconds.

> Make the 2D cartoon look with a scientist and a volcano instead, night sky, captions in yellow.

> Make me a 20-second vertical Short in the toon-3D cartoon-trivia style (like the railroad example): five scenes, cuts every few seconds, one caption word at a time. The story: why lighthouses are painted in stripes. My captions: ...

> Take the railroad Short example and change the story to the Great Molasses Flood: a city street set, a tank, people running, same captions style.

> Make me the size comparison shot from the video with: a cat 0.25 m, a horse 1.6 m, a bus 3.5 m, the Statue of Liberty 93 m. 7 seconds.

> Make the planets shot but make the planet red like Mars, no moon, 5 seconds.

> Make the falling-blocks physics shot in my brand colours #FF3B3B and #111111.

> Make the subscriber bars shot with my numbers: 2024 3,200 / 2025 41,000 / 2026 180,000.

> Make the map route shot for NEW YORK, CHICAGO, DENVER, LOS ANGELES with the line "2026 · THE ROAD TRIP".

> Make the phone mockup shot with my app name and price $9/month.

## Shot ideas

**Titles and intros**
> Make a 3D intro title for my channel: CHANNEL NAME, with a smaller line under it that says NEW VIDEO EVERY FRIDAY. Dark stage, slow push in, 6 seconds.

> Make a chapter card that says STEP 2: THE SCRIPT. 4 seconds, the words swing up one by one.

**Numbers**
> Make a shot where a gold number counts up to $18,689 and lands at 2.4 seconds, with PAID OUT IN 90 DAYS under it. 5 seconds.

> Make a counter from 0 to 1,000,000 VIEWS that lands at 3 seconds, white digits, blue accent.

**Photos and dates**
> Fan out these three photos in depth with a date card that says MARCH 28, 2026 landing at 1.8 seconds: C:\path\one.jpg, C:\path\two.jpg, C:\path\three.jpg. 5 seconds.

**Lower thirds and labels (over your footage)**
> Make a lower third with transparency: name JOHN SMITH, role FOUNDER, CLIPWORKS. 5 seconds, in and out by itself.

> Make a transparent price label that says $29/MONTH, bottom right, 4 seconds.

**Comparisons and quotes**
> Make a before/after shot: on the left OLD WAY with 3 hours per video, on the right NEW WAY with 20 minutes per video. The right side lights up at 2.5 seconds. 6 seconds.

> Put this screenshot on a 3D plane and push in on it slowly, dark background, 5 seconds: C:\path\tweet.png

**Logos**
> Reveal my logo on a dark stage with a light sweep, 4 seconds: C:\path\logo.png

## Changing a shot

> Make the gold word bigger and move the camera a bit lower. Stills again.

> Land the number at 3.1 seconds instead.

> Change the accent colour to #FF3B3B.

> Use this font for the small line: Anton.

> Make it 1080x1920 vertical for a Short.   (Claude passes --size 1080x1920)

> Give me a version with no camera shake.

## Copy a channel's style (your hook or key moments)

> Here's a video whose look I love: https://www.youtube.com/watch?v=XXXX . Make my hook in that style. My voiceover is C:\Users\YOU\Videos\hook.wav and my script is in hook.txt. Vertical Short.

> Make the moment where I say "and then the bridge collapsed" in the style of this video: C:\Users\YOU\Downloads\reference.mp4. Show me stills next to the reference first.

> Give me the same clip without my voice so I can put it under my own audio track.

> I don't have an example. What styles can you do? Make my intro in the space documentary style. Here's my script: ...

> Make a 30-second cartoon Short about why airplanes have tiny windows. Write the script first and show me.

(Claude studies the reference frame by frame, writes a style card, times every shot to your voice, and compares its stills with the reference before rendering. It copies the look, never their logo, characters, text, music or topic. No example? Pick one of the ready-made styles (a cartoon Short or a space documentary). No voiceover yet? A script or even just a topic works: Claude writes the script first and shows you. It builds your hook or a few key moments, about a minute per request: a whole video this way would use far more Claude usage than a session has, so the rest stays in your normal edit.)

## Timing to your voice

> The word "ten thousand" is at 0:07.4 in my voiceover and the shot starts at 0:05.0. Land the number when I say it.

(Claude works out 2.4 seconds into the shot. If you don't know the second, read it off your editor's timeline.)

## Speed and quality

> How long will this render take on my computer?

> It looks noisy. Fix the lighting, not the samples.

> The render stopped because it was going to take too long. What can we simplify?

(Claude will only render past the 15-minute guard if you say "I accept the wait".)

## Trouble

> Blender crashed half way. Continue the render.   (finished frames are reused)

> Stop all renders.

> Something is off. Run the doctor and tell me what's missing.

> Update the kit from C:\Users\YOU\Downloads\Blender-Kit-1-Setup.zip
