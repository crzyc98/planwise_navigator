import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**'],
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: {
      'react-hooks': reactHooks,
    },
    // Existing dependency findings are recorded in eslint-suppressions.json;
    // new Rules of Hooks or exhaustive-deps violations still fail the build.
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
    },
  },
  {
    // Pages under /w/:workspaceId must keep the workspace in every link. A bare
    // path falls through to the legacy redirect, which opens whichever workspace
    // the browser last stored and can be another client's (#1198).
    files: ['components/**/*.{ts,tsx}'],
    ignores: ['**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-imports': ['error', {
        paths: [{
          name: 'react-router-dom',
          importNames: ['useNavigate'],
          message: 'Use useWorkspaceNavigate from hooks/useWorkspaceNavigation so the link stays in the current workspace.',
        }],
      }],
      'no-restricted-syntax': ['error', {
        selector: "JSXOpeningElement[name.name=/^(Link|NavLink|Navigate)$/] > JSXAttribute[name.name='to'] :matches(Literal[value=/^\\u002F(?!w\\u002F)/], TemplateLiteral[quasis.0.value.raw=/^\\u002F(?!w\\u002F)/])",
        message: 'This path drops the workspace. Use WorkspaceLink, or build the path with useWorkspacePath.',
      }],
    },
  },
);
