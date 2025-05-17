<h1 align="center">Auto Watch Later</h1>

## Table of Contents
- [About](#about)
- [Built Using](#built_using)
- [Authors](#authors)
- [Acknowledgments](#acknowledgement)

## About <a name = "about"></a>
I watch YouTube on almost a daily basis, so I wanted a way to automatically add my subscriptions to a custom playlist so I can add them to the YouTube built-in Watch Later playlist. The YouTube Data API v3 doesn't let you mess with Watch Later directly, so I have to use a temp playlist and add all videos to Watch Later from there, which is just a "Add all to..." button in the playlist settings on the YouTube desktop website.

### Why? <a name = "why"></a>
1. Since I have about 200 subscriptions, I get a lot of video notifications on my phone, and Android will start removing older notifications from the same app once you get too many, and I'd rather not miss any videos.
2. The "Add to Watch Later" notification action doesn't work on mobile data unless the YouTube app is open, which is really annoying.

The drawback is I'm getting every single video/short/livestream from all my subscriptions, whereas I used to be able to filter out anything I'm not interested in based on title/thumbnail/type. I don't mind clearing out videos from the playlist as I'm watching videos, I'll occasionally skip over a video anyways if I don't want to watch it, so I'll take this over missing videos.

### Note <a name = "note"></a>
I whipped this up by [vibe-coding](https://en.wikipedia.org/wiki/Vibe_coding) in [Claude](https://claude.ai/). I've heard anecdotally that Claude tends to do better at coding tasks than other LLMs, so this project was a way to see if that's true.

## Built Using <a name = "built_using"></a>
- [Python](https://www.python.org/)
- [Claude](https://claude.ai/)

## Authors <a name = "authors"></a>
- [@Noahffiliation](https://github.com/Noahffiliation) - Idea & Initial work

## Acknowledgements <a name = "acknowledgement"></a>
- YouTube
