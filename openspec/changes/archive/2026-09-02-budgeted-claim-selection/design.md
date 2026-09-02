# Design — budgeted-claim-selection

## Deriving a footprint without inventing one

The refusal at the heart of `claim-selection` is that a claim's footprint must not be matched out
of its free text. That refusal is about *evidence*, not about automation: a `quantity` string is
prose, and a parameter name found in prose is a coincidence dressed as a dependency.

A model is not prose. For an SBML-backed dossier the dependency is a fact the file states: the
claim's target resolves to a species or observable, that element's rate law names parameters and
other species, and those name more in turn. The transitive closure is the set of things whose value
changes the claim's verdict — which is the definition the objective needs.

Two consequences follow, and both are deliberate:

- **The derivation is structural, so it is only as complete as the model.** A claim resting on an
  unstated dosing protocol depends on something the model does not contain. That is why gaps are
  part of the footprint: the closure a reconstruction has to invent is exactly the kind of shared
  upstream assumption two claims can rest on together, and it is the kind the paper is most likely
  to have left out.
- **Derived and extracted footprints are not interchangeable.** A structural footprint says what the
  *model* makes the claim depend on. A curator's footprint can say what the *paper's argument*
  makes it depend on, which is sometimes broader. Recording which is which keeps a selection's
  defence honest, and lets a later round measure whether they agree.

## Why the certificate has to change

A budget makes a certificate's silence load-bearing. Today a claim absent from a certificate is a
claim the paper did not make; under a budget it may be a claim somebody chose not to run. Those two
readings cannot share a representation, and the second is the one that lets a paper look reproduced
on a third of its results.

The existing qualification machinery is the right shape for this: a load-bearing assumption already
forbids an unqualified `reproduced`, for the same reason — the verdict rests on something other
than the paper's own content. An unattempted claim is a stronger version of the same fact.

## Fences

Extracting a paper's claims from its manuscript remains out of scope. This change makes the claims
Reprolith *already holds* selectable on their merits; it does not increase how many it holds. The
corpus number the finding note must state is what share of existing claims the derivation reached,
and it will not be all of them.
