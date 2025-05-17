<h1 align="center">Auto Watch Later</h1>

## Table of Contents
- [About](#about)
- [Built Using](#built_using)
- [Authors](#authors)
- [Acknowledgments](#acknowledgement)

## About <a name = "about"></a>
I watch YouTube on almost a daily basis, so I wanted a way to automatically add my subscriptions to a custom playlist so I can add to the YouTube built-in Watch Later playlist. The YouTube Data API v3 doesn't let you mess with Watch Later directly, so I have to use a temp playlist and add all videos to Watch Later from there. I have a few reasons for automating this: Since I have about 200 subscriptions, I get a lot of video notifications on my phone, and Android will start removing older notifications from the same app once you get too many. Also, the "Add to Watch Later" notification action doesn't work on mobile data unless the YouTube app is open. All that is too much work to do throughout the day. I usually can filter out some videos I know I don't want to watch based on the title/thumbnail, but I don't mind just skipping over the video or pre-clearing the playlist as I go.

### Note <a name = "note"></a>
I whipped this up by [vibe-coding](https://en.wikipedia.org/wiki/Vibe_coding) in [Claude](https://claude.ai/). I've heard anecdotally that Claude tends to do better at coding tasks than other LLMs, so this project was a way to see if that's true.

## Built Using <a name = "built_using"></a>
- [Python](https://www.python.org/)
- [Claude](https://claude.ai/)

## Authors <a name = "authors"></a>
- [@Noahffiliation](https://github.com/Noahffiliation) - Idea & Initial work

## Acknowledgements <a name = "acknowledgement"></a>
- YouTube
