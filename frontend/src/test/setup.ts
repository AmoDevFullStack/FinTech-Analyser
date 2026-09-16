import "@testing-library/jest-dom/vitest";

// jsdom implements no layout, so it ships no scrollIntoView. Stubbed here rather than
// guarded in components: keeping a scroll call out of a component because of a test
// environment would put the environment in charge of the code.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
