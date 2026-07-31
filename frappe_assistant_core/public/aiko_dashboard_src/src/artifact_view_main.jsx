import "polyfill-crypto-methods";
import "./frappe-mock";
import React from "react";
import { createRoot } from "react-dom/client";
import { ArtifactView } from "./components/ArtifactView";
import "@openuidev/react-ui/styles/index.css";
import "@openuidev/react-ui/defaults.css";
import "./styles.css";

window.AikoDashboardArtifact = {
  mount(el, artifactName) {
    const root = createRoot(el);
    root.render(<ArtifactView artifactName={artifactName} />);
  },
};
