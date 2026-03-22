"""Step through GIF frames interactively using matplotlib."""

import sys
import glob
import os
from PIL import Image
import matplotlib.pyplot as plt


def step_through_gif(path: str) -> None:
    img = Image.open(path)
    frames = []
    try:
        while True:
            frames.append(img.copy())
            img.seek(img.tell() + 1)
    except EOFError:
        pass

    if not frames:
        print(f"No frames found in {path}")
        return

    idx = [0]
    fig, ax = plt.subplots()
    fig.suptitle(os.path.basename(path))
    im = ax.imshow(frames[0])
    title = ax.set_title(f"Frame {1}/{len(frames)}")
    ax.axis("off")

    def update(new_idx: int) -> None:
        idx[0] = new_idx % len(frames)
        im.set_data(frames[idx[0]])
        title.set_text(f"Frame {idx[0] + 1}/{len(frames)}")
        fig.canvas.draw_idle()

    def on_key(event):
        if event.key in ("right", " "):
            update(idx[0] + 1)
        elif event.key == "left":
            update(idx[0] - 1)
        elif event.key == "home":
            update(0)
        elif event.key == "end":
            update(len(frames) - 1)
        elif event.key in ("q", "escape"):
            plt.close(fig)

    fig.canvas.mpl_connect("key_press_event", on_key)
    print(f"Showing {len(frames)} frames. Keys: Right/Space=next, Left=prev, Home/End, Q=quit")
    plt.show()


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if len(sys.argv) > 1:
        paths = sys.argv[1:]
    else:
        paths = sorted(glob.glob(os.path.join(script_dir, "*.gif")))

    if not paths:
        print("No GIF files found. Pass paths as arguments or place .gif files next to this script.")
        sys.exit(1)

    for path in paths:
        print(f"\nOpening: {path}")
        step_through_gif(path)


if __name__ == "__main__":
    main()
