"use client";

import { useState } from "react";

import { IconLock, IconShield } from "@/components/Icons";
import { ThemeSelector } from "@/components/ThemeToggle";
import { Card, Chip, PageHeader } from "@/components/ui";
import { API_URL } from "@/lib/api";
import { useConversations } from "@/lib/hooks";
import { isRealSource } from "@/lib/integrations";
import { DEFENSES_DETAIL, DEFENSES_LABEL, SERVER_LABEL } from "@/lib/labels";
import { clearAll } from "@/lib/runner";
import { useHealth } from "@/lib/useHealth";

export default function SettingsView() {
  const { health, down, refresh } = useHealth();
  const conversations = useConversations();
  const [confirming, setConfirming] = useState(false);
  const [cleared, setCleared] = useState<number | null>(null);

  return (
    <div className="page page-narrow">
      <PageHeader eyebrow="Système" title="Réglages" lead="Préférences de cette interface et état de la connexion à l'API locale." />

      <Card title="Apparence">
        <div className="setting">
          <div>
            <p className="setting-name">Thème</p>
            <p className="muted small">Clair, sombre ou selon le système. Mémorisé dans ce navigateur, appliqué immédiatement.</p>
          </div>
          <ThemeSelector />
        </div>
      </Card>

      <Card
        title="Connexion à l'API"
        action={
          <button type="button" className="btn btn-ghost btn-small" onClick={() => void refresh()}>
            Revérifier
          </button>
        }
      >
        <dl className="facts facts-wide">
          <div>
            <dt>Adresse</dt>
            <dd>
              <code>{API_URL}</code> <span className="muted small">(locale uniquement ; modifiable par NEXT_PUBLIC_API_URL)</span>
            </dd>
          </div>
          <div>
            <dt>État</dt>
            <dd>{down ? <Chip tone="bad">injoignable</Chip> : health ? <Chip tone="ok">connectée</Chip> : <Chip>vérification…</Chip>}</dd>
          </div>
          {health && (
            <>
              <div>
                <dt>Modèle</dt>
                <dd>{health.model === "demo" ? "Démo (réponses simulées)" : (health.llm ?? "Modèle réel")}</dd>
              </div>
              <div>
                <dt>Défenses</dt>
                <dd>
                  <IconShield size={13} /> {DEFENSES_LABEL[health.defenses]} <span className="muted small">— {DEFENSES_DETAIL[health.defenses]}</span>
                </dd>
              </div>
              <div>
                <dt>Serveurs</dt>
                <dd className="facts-tags">
                  {health.servers.map((s) => (
                    <Chip key={s} tone={isRealSource(s, health) ? "accent" : undefined}>
                      {SERVER_LABEL[s]} · {isRealSource(s, health) ? "réel" : "test"}
                    </Chip>
                  ))}
                </dd>
              </div>
            </>
          )}
        </dl>
        <p className="muted small card-foot">
          Modèle, défenses et sources se choisissent au lancement de l&apos;API (options de run_api.py) : l&apos;interface les affiche sans
          pouvoir les modifier.
        </p>
      </Card>

      <Card title="Données locales">
        <div className="setting">
          <div>
            <p className="setting-name">Conversations enregistrées</p>
            <p className="muted small">
              {conversations === null ? "…" : `${conversations.length} conversation${conversations.length > 1 ? "s" : ""}`} dans ce navigateur
              uniquement (50 au maximum). L&apos;API ne les conserve pas.
            </p>
            {cleared !== null && <p className="small ok-text">{cleared} conversation{cleared > 1 ? "s" : ""} supprimée{cleared > 1 ? "s" : ""}.</p>}
          </div>
          {confirming ? (
            <div className="row">
              <button
                type="button"
                className="btn btn-danger btn-small"
                onClick={() => {
                  setCleared(clearAll());
                  setConfirming(false);
                }}
              >
                Tout supprimer
              </button>
              <button type="button" className="btn btn-ghost btn-small" onClick={() => setConfirming(false)}>
                Annuler
              </button>
            </div>
          ) : (
            <button type="button" className="btn btn-secondary btn-small" disabled={!conversations?.length} onClick={() => setConfirming(true)}>
              Effacer l&apos;historique
            </button>
          )}
        </div>
      </Card>

      <Card title="Compte et sécurité">
        <div className="setting">
          <span className="empty-icon">
            <IconLock />
          </span>
          <div>
            <p className="setting-name">Application locale, sans compte</p>
            <p className="muted small">
              AgentFlow tourne sur votre machine (127.0.0.1) pour un seul utilisateur : pas d&apos;inscription, de profil ni de session à
              gérer. Les accès Google et GitHub restent distincts : jetons à portée minimale gérés côté serveur, jamais transmis au
              navigateur.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
