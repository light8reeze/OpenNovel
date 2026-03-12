use std::{fs, path::Path};

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Location {
    pub id: String,
    pub name: String,
    pub description: String,
    pub connections: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Npc {
    pub id: String,
    pub name: String,
    pub location_id: String,
    pub role: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuestStage {
    pub stage: u32,
    pub summary: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuestDefinition {
    pub id: String,
    pub title: String,
    pub stages: Vec<QuestStage>,
    pub endings: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct ContentBundle {
    pub locations: Vec<Location>,
    pub npcs: Vec<Npc>,
    pub sunken_ruins: QuestDefinition,
}

impl ContentBundle {
    pub fn load_from_disk(root: impl AsRef<Path>) -> Result<Self, String> {
        let root = root.as_ref();
        let locations: Vec<Location> = read_json(root.join("locations.json"))?;
        let npcs: Vec<Npc> = read_json(root.join("npcs.json"))?;
        let sunken_ruins: QuestDefinition =
            read_json(root.join("quests").join("sunken_ruins.json"))?;

        for location in &locations {
            for connection in &location.connections {
                if !locations
                    .iter()
                    .any(|candidate| &candidate.id == connection)
                {
                    return Err(format!(
                        "location '{}' references unknown connection '{}'",
                        location.id, connection
                    ));
                }
            }
        }

        for npc in &npcs {
            if !locations
                .iter()
                .any(|location| location.id == npc.location_id)
            {
                return Err(format!(
                    "npc '{}' references unknown location '{}'",
                    npc.id, npc.location_id
                ));
            }
        }

        Ok(Self {
            locations,
            npcs,
            sunken_ruins,
        })
    }

    pub fn location_name(&self, location_id: &str) -> String {
        self.locations
            .iter()
            .find(|location| location.id == location_id)
            .map(|location| location.name.clone())
            .unwrap_or_else(|| location_id.to_string())
    }
}

fn read_json<T: for<'de> Deserialize<'de>>(path: impl AsRef<Path>) -> Result<T, String> {
    let path = path.as_ref();
    let data = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    serde_json::from_str(&data)
        .map_err(|error| format!("failed to parse {}: {}", path.display(), error))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn content_loads_from_repo_files() {
        let bundle = ContentBundle::load_from_disk(repo_content_root()).expect("content loads");
        assert!(bundle.locations.len() >= 3);
        assert!(bundle.npcs.iter().any(|npc| npc.id == "caretaker"));
        assert_eq!(bundle.sunken_ruins.id, "sunken_ruins");
    }

    fn repo_content_root() -> std::path::PathBuf {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../content")
            .canonicalize()
            .expect("repo content dir")
    }
}
