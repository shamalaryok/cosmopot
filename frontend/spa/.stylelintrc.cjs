module.exports = {
  extends: ["stylelint-config-standard", "stylelint-config-recommended-vue"],
  plugins: ["stylelint-order"],
  rules: {
    "color-no-invalid-hex": true,
    "order/properties-alphabetical-order": true,
    "selector-class-pattern": null,
    "media-feature-range-notation": null,
  },
  overrides: [
    {
      files: ["**/*.vue"],
      customSyntax: "postcss-html",
    },
  ],
};
