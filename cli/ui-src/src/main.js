// Latin-only subset: this UI's text is English, and pulling the unrestricted
// (all-subset) imports bundles cyrillic/greek/vietnamese glyphs for nothing.
import '@fontsource/space-grotesk/latin-400.css';
import '@fontsource/space-grotesk/latin-500.css';
import '@fontsource/space-grotesk/latin-600.css';
import '@fontsource/space-grotesk/latin-700.css';
import '@fontsource/jetbrains-mono/latin-400.css';
import '@fontsource/jetbrains-mono/latin-500.css';
import './style.css';
import { initSidebar } from './sidebar.js';
import { mountExplore } from './views/explore.js';
import { mountRegistry, loadRegistry } from './views/registry.js';
import { mountStats, loadStats } from './views/stats.js';

const mounted = { explore: false, registry: false, stats: false };

function showView(name) {
  if (name === 'explore' && !mounted.explore) {
    mountExplore(document.getElementById('view-explore'));
    mounted.explore = true;
  } else if (name === 'registry') {
    if (!mounted.registry) { mountRegistry(document.getElementById('view-registry')); mounted.registry = true; }
    else loadRegistry();
  } else if (name === 'stats') {
    if (!mounted.stats) { mountStats(document.getElementById('view-stats')); mounted.stats = true; }
    else loadStats();
  }
}

initSidebar(showView);
showView('explore');
