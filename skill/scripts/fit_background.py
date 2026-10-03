"""Reconstruct a slide's background from the pixels the cards do NOT cover,
then derive each card's translucent fill as a vertical gradient.

Why this exists
---------------
Brand slides usually sit on a soft multi-stop gradient (often a corner glow).
Drawing that with a DrawingML gradient is hopeless; but the slide's own margins
and the gaps between cards ARE pure background.  Fit a smooth polynomial to
those pixels, rasterise it, and use it as the backdrop image.  Then each card's
fill is whatever makes the observed interior match:

    composite = (1-a)*bg + a*C   ->   C = bg + (obs - bg) / a

Sampling one content-free column per card and fixing a(y) from a0 to a1 yields
a 4-5 stop vertical gradient that reproduces the card at that column and still
lets the background show through horizontally.

Usage
-----
    from fit_background import BackgroundFit
    fit = BackgroundFit("slide_full.png", cards=[(x0,y0,x1,y1), ...],
                        text_cuts=[(x0,y0,x1,y1), ...])
    fit.save("bg_fit.png")
    print(fit.overlay_stops(rect=(7.81,13.89,47.45,82.87), sample_x=45.2))
"""
import numpy as np
from PIL import Image


class BackgroundFit:
    def __init__(self, img_path, cards, text_cuts=(), deg=6, pad=0.4, stride=3):
        im = Image.open(img_path).convert("RGB")
        self.a = np.asarray(im).astype(float)
        self.H, self.W, _ = self.a.shape
        yy, xx = np.mgrid[0:self.H, 0:self.W]
        self.X, self.Y = xx / self.W, yy / self.H

        m = np.ones((self.H, self.W), bool)
        for x0, y0, x1, y1 in list(cards) + list(text_cuts):
            m[int((y0 - pad) / 100 * self.H):int((y1 + pad) / 100 * self.H),
              int((x0 - pad) / 100 * self.W):int((x1 + pad) / 100 * self.W)] = False
        self.mask_px = int(m.sum())

        # subsample: a degree-6 fit is smooth, so every Nth pixel is plenty and
        # keeps a 4K slide well under a second.
        sl = (slice(None, None, stride), slice(None, None, stride))
        self.sl = sl
        ms = m[sl]
        self.terms = [(i, j) for i in range(deg + 1) for j in range(deg + 1) if i + j <= deg]
        Amat = self._design(self.X[sl][ms], self.Y[sl][ms])
        self.coef = []
        for c in range(3):
            b = self.a[sl][:, :, c][ms]
            sol, *_ = np.linalg.lstsq(Amat, b, rcond=None)
            self.coef.append(sol)
            pred = Amat @ sol
            self.rmse = float(np.sqrt(((pred - b) ** 2).mean()))

    # ------------------------------------------------------------------ #
    def _design(self, xs, ys):
        return np.stack([(xs ** i) * (ys ** j) for (i, j) in self.terms], axis=1)

    def value(self, xp, yp):
        v = self._design(np.array([xp / 100.0]), np.array([yp / 100.0]))[0]
        return np.array([v @ self.coef[c] for c in range(3)])

    def observed(self, xp, yp, r=0.12):
        Xc, Yc = int(xp / 100 * self.W), int(yp / 100 * self.H)
        R = max(1, int(r / 100 * self.W))
        return self.a[Yc - R:Yc + R + 1, Xc - R:Xc + R + 1].reshape(-1, 3).mean(axis=0)

    def render(self, grid=(960, 540)):
        gw, gh = grid
        XX, YY = np.meshgrid((np.arange(gw) + 0.5) / gw, (np.arange(gh) + 0.5) / gh)
        A = self._design(XX.ravel(), YY.ravel())
        out = np.stack([(A @ self.coef[c]).reshape(gh, gw) for c in range(3)], axis=2)
        return np.clip(out, 0, 255).astype(np.uint8)

    def save(self, path, size=(1920, 1080)):
        img = Image.fromarray(self.render())
        if size:
            img = img.resize(size, Image.LANCZOS)
        img.save(path)
        return path

    # ------------------------------------------------------------------ #
    def overlay_stops(self, rect, sample_x, nt=5, a0=0.20, a1=0.55, inset=1.0):
        """Vertical gradient stops [(pos%, '#RRGGBB', alpha%), ...] for a card.

        rect      = (x0, y0, x1, y1) of the card in percent
        sample_x  = a column inside the card free of text/icons
        """
        x0, y0, x1, y1 = rect
        out = []
        for i in range(nt):
            t = i / (nt - 1)
            y = min(max(y0 + (y1 - y0) * t, y0 + inset), y1 - inset)
            obs = self.observed(sample_x, y)
            b = self.value(sample_x, y)
            a = a0 + (a1 - a0) * t
            C = np.clip(b + (obs - b) / a, 0, 255)
            out.append((round(t * 100), "#%02X%02X%02X" % (int(C[0]), int(C[1]), int(C[2])),
                        round(a * 100)))
        return out

    def report(self):
        return {"background_px": self.mask_px, "rmse": round(self.rmse, 2), "terms": len(self.terms)}


if __name__ == "__main__":
    import sys, json
    cards = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
    fit = BackgroundFit(sys.argv[1], cards)
    print(json.dumps(fit.report(), indent=1))
    fit.save("bg_fit.png")
