---
title: How to use GIMP for figure processing
layout: post
post-image: "https://raw.githubusercontent.com/fabian-kutschera/fabian-kutschera.github.io/master/assets/images/1280x720%20Placeholder.png"
description: This post explains how GIMP can be used to process figures (format size, blur image, insert title, etc.), such that they fit the required standard for blog posts.
tags:
- how to
- gimp
- blog
---

Below I introduce the steps how the figure of this [blog post](2023-03-25-kinematic-motion-anatolia.md) was generated, with the white bold title overlaying the blurred image. Since the post *Present-day kinematic motion of Anatolia* links global and regional plate tectonics, I searched for a related figure and came across an interesting article in [Science](https://www.science.org/content/article/slowdown-plate-tectonics-may-have-led-earth-s-ice-sheets), which displays a color-coded mid-ocean ridge. 

I was lucky, because this figure has already the required size of **1280x720**, otherwise a rescaling would have been necessary to avoid showing a distored figure in the blog post. However, changing/extracting the preferred size of a *.png* figure is also easily possible with [GIMP](https://www.gimp.org), a free & open-source image editor (I used the most recent version 2.10.34).

1. Load the *.png* figure into GIMP.

2. Check the size of the figure (should be 1280x720).

3. Place a textbox over the entire figure and select centering. Adjust the color...

4. Select *Export as* and choose again *.png*
