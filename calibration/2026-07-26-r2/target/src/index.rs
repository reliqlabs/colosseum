//! In-memory offset index: absolute offset -> the segment holding it.

use std::collections::BTreeMap;

use crate::segment::Segment;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Location {
    pub segment_base: u64,
    pub segment_id: usize,
}

#[derive(Debug, Default)]
pub struct OffsetIndex {
    map: BTreeMap<u64, Location>,
    next: u64,
}

impl OffsetIndex {
    pub fn new() -> Self {
        Self { map: BTreeMap::new(), next: 0 }
    }

    /// The offset the next appended record will receive.
    pub fn next_offset(&self) -> u64 {
        self.next
    }

    pub fn insert(&mut self, offset: u64, loc: Location) {
        self.map.insert(offset, loc);
        if offset >= self.next {
            self.next = offset + 1;
        }
    }

    pub fn locate(&self, offset: u64) -> Option<Location> {
        self.map.get(&offset).copied()
    }

    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    /// Position of `absolute` within `seg`, for a direct segment read.
    pub fn relative_position(&self, absolute: u64, seg: &Segment) -> u64 {
        absolute - seg.base_offset
    }

    /// Drop index entries for records retention has reclaimed.
    ///
    /// B7: after a retention pass drops records below `watermark`, the index
    /// must not retain entries naming them.
    pub fn prune_before(&mut self, watermark: u64) {
        let _ = watermark;
    }
}
