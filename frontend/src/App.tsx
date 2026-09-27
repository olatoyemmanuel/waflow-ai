import { BrowserRouter } from "react-router-dom";

import { AppProviders } from "./app/providers";
import { AppRouter } from "./app/router";

/**
 * Root WAFlow AI application component.
 *
 * Responsibilities:
 * - initialize application-wide providers
 * - initialize client-side routing
 * - render the application's route tree
 */
function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <AppRouter />
      </BrowserRouter>
    </AppProviders>
  );
}

export default App;