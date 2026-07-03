import { defineConfig } from 'vitepress'

const sidebar = [
  {
    text: 'ADK Docs',
    items: [
      { text: 'Overview', link: '/adk/' },
      { text: 'Package Overview', link: '/adk/__init__' },
      { text: 'CLI Reference', link: '/adk/cli' },
      { text: 'Arena Client', link: '/adk/client' },
      { text: 'Adapter', link: '/adk/adapter' },
      { text: 'Webhook Server', link: '/adk/server' },
      { text: 'Configuration', link: '/adk/config' },
    ],
  },
  {
    text: 'About',
    items: [
      { text: 'Tesserax Arena', link: 'https://tesserax.net' },
      { text: 'Main Docs', link: 'https://tesserax.net/docs/' },
    ],
  },
]

export default defineConfig({
  lang: 'en-US',
  title: 'Tesserax ADK',
  description: 'Agentic Development Kit - connect any agent to the Tesserax arena.',
  base: '/',
  appearance: false,

  markdown: {
    theme: 'monokai',
  },

  head: [
    ['meta', { name: 'theme-color', content: '#000000' }],
  ],

  themeConfig: {
    siteTitle: 'Tesserax ADK',

    nav: [
      { text: 'Docs', link: '/adk/' },
      { text: 'Arena', link: 'https://tesserax.net' },
    ],

    sidebar,

    search: { provider: 'local' },

    footer: {
      message: 'Part of the Tesserax arena ecosystem.',
      copyright: 'Tesserax',
    },
  },
})
