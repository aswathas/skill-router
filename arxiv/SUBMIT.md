# Publishing this paper on arXiv

Everything in this directory is generated. Nothing here needs editing by hand.

## What is here

| file | what it is |
|---|---|
| `metadata.yaml` | the submission form values: title, authors, abstract, categories, comments |
| `eprint/` | the LaTeX source arXiv compiles |
| `skill-router-eprint.tar.gz` | the archive to upload |
| `make-metadata.py` | regenerates `metadata.yaml` from `paper/content.py` |
| `make-eprint.py` | regenerates the source directory and the tarball |

## Before you submit

1. **Rebuild everything.** The metadata and the tarball are copies; if the
   paper changed, they are stale.

   ~~~bash
   cd paper && python build.py && cd ..
   python arxiv/make-metadata.py
   python arxiv/make-eprint.py
   ~~~

2. **Check the abstract matches.** `metadata.yaml` takes the abstract straight
   from `paper/content.py`, so it always does. arXiv warns when the form
   abstract and the PDF abstract differ.

3. **Check the licence.** The artefact repository is MIT. The paper itself is
   distributed under arXiv's default licence unless you choose CC BY on the
   submission form. Pick CC BY 4.0 if you want reuse rights on the paper
   itself; the two choices are independent.

4. **Check the category.** Primary `cs.AI`, cross-listed `cs.IR`. If you
   prefer `cs.SE` (Software Engineering), the venue matters more than the
   category: a systems audience reads `cs.SE` and an ML audience reads
   `cs.AI`.

## Submitting

1. Sign in at https://arxiv.org/login (you need an arXiv account; the
   affiliation email must be institutional or a recognised email domain, or
   the submission is held for moderation).
2. Go to https://arxiv.org/abs and choose "Submit new paper".
3. Upload `skill-router-eprint.tar.gz` as the source archive.
4. Paste the values from `metadata.yaml` into the form.
5. Under "Comments", use:

   ~~~text
   7 pages, 9 tables. Public artefact (router, capability taxonomy, 298-case
   evaluation harness and benchmark): https://github.com/aswathas/skill-router
   ~~~

6. Submit. arXiv compiles the source with its own TeX engine, which provides
   `acmart`, so no extra style files are needed. The bibliography is written as
   inline `\bibitem` entries, so no `.bbl` file is needed either.

## After acceptance

- Add the arXiv id to the repository README and to the paper's own PDF.
- Link the arXiv record from the GitHub repository description.
- If you want it at a venue rather than only as a preprint, the ACM
  conference cycle and its workshop tracks are the natural target for a
  systems paper of this shape; the same source compiles unchanged.

## If arXiv refuses the source

The one dependency is `acmart`, which arXiv provides. If a build fails, the
usual cause is the `\acmConference` line (it names a workshop that does not
exist). Delete that line and the `\acmBooktitle` line, rebuild, and resubmit:
the paper still compiles and still looks like an ACM paper.
