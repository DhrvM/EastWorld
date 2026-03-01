<template>
  <q-layout view="lHh Lpr lFf" class="bg-dark text-white font-inter">
    <q-header class="bg-dark text-white q-py-sm border-bottom-subtle">
      <q-toolbar class="flex flex-center">
        <q-toolbar-title class="text-h4 text-weight-bold tracking-wide text-center">
          Eastworld
        </q-toolbar-title>
      </q-toolbar>
    </q-header>
    
    <q-page-container>
      <q-page>
        <IndexPage />
        
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import IndexPage from 'src/pages/IndexPage.vue';

</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');

.font-inter {
  font-family: 'Inter', sans-serif;
}
.tracking-wide {
  letter-spacing: 0.05em;
}
.border-bottom-subtle {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
</style>
