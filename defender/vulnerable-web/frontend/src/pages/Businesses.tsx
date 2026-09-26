import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MapPin, Search, Star } from "lucide-react";
import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Input } from "../components/ui/input";
import axiosInstance from "../services/axios";

export type Business = {
  id: number;
  owner: number | null;
  owner_username?: string;
  name: string;
  description: string;
  category: string;
  address: string;
  verified: boolean;
  average_rating: number | null;
  created_at: string;
};

export default function Businesses() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const activeCategory = searchParams.get("category") || "";
  const [categories, setCategories] = useState<
    { value: string; label: string }[]
  >([]);

  const fetchBusinesses = async (query?: string) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (query && query.trim().length > 0) params.set("q", query.trim());
      if (activeCategory) params.set("category", activeCategory);
      
      const sort = searchParams.get("sort");
      if (sort) params.set("ordering", sort);

      const endpoint = `businesses/${
        params.toString() ? `?${params.toString()}` : ""
      }`;
      const response = await axiosInstance.get(endpoint);
      setBusinesses(response.data.results || response.data);
      setError(null);
    } catch (err) {
      setError("Failed to fetch businesses");
      console.error("Error fetching businesses:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBusinesses();
    (async () => {
      try {
        const res = await axiosInstance.get("businesses/categories/");
        setCategories(res.data || []);
      } catch {
        // ignore
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchBusinesses(searchQuery || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCategory, searchParams]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchBusinesses(searchQuery || undefined);
  };

  const handleReset = () => {
    setSearchQuery("");
    fetchBusinesses(undefined);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <div className="text-lg">Loading businesses...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <div className="text-lg text-destructive">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <h1 className="text-3xl font-bold">Businesses</h1>

        <div className="flex items-center gap-4">
          <DropdownMenu>
            <DropdownMenuTrigger className="px-4 py-2 rounded-md border text-sm">
              {activeCategory
                ? categories.find((c) => c.value === activeCategory)?.label ||
                  "Category"
                : "Categories"}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" sideOffset={6}>
              <DropdownMenuItem
                onClick={() =>
                  setSearchParams((prev) => {
                    const copy = new URLSearchParams(prev);
                    copy.delete("category");
                    return copy;
                  })
                }
              >
                Show all
              </DropdownMenuItem>
              {categories.map((c) => (
                <DropdownMenuItem
                  key={c.value}
                  onClick={() =>
                    setSearchParams((prev) => {
                      const copy = new URLSearchParams(prev);
                      copy.set("category", c.value);
                      return copy;
                    })
                  }
                >
                  {c.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <form onSubmit={handleSearch} className="flex gap-2 w-full sm:w-auto">
            <div className="relative flex-1 sm:w-64">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
              <Input
                type="text"
                placeholder="Search businesses..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <Button type="submit">Search</Button>
            {searchQuery && (
              <Button type="button" variant="outline" onClick={handleReset}>
                Clear
              </Button>
            )}
          </form>

          <DropdownMenu>
            <DropdownMenuTrigger className="px-4 py-2 rounded-md border text-sm flex items-center gap-2">
              Sort
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setSearchParams(prev => { const p = new URLSearchParams(prev); p.set("sort", "-created_at"); return p; })}>Newest</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSearchParams(prev => { const p = new URLSearchParams(prev); p.set("sort", "created_at"); return p; })}>Oldest</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSearchParams(prev => { const p = new URLSearchParams(prev); p.set("sort", "name"); return p; })}>Name (A-Z)</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSearchParams(prev => { const p = new URLSearchParams(prev); p.set("sort", "-name"); return p; })}>Name (Z-A)</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {businesses.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-muted-foreground">No businesses found.</p>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {businesses.map((business) => (
            <Link
              key={business.id}
              to={`/business/${business.id}`}
              className="block group"
            >
              <Card className="h-full hover:shadow-lg transition-shadow cursor-pointer border-transparent group-hover:border-primary/20">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-xl group-hover:text-primary transition-colors">
                      {business.name}
                    </CardTitle>
                    {business.verified && (
                      <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">
                        Verified
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <span className="capitalize">{business.category}</span>
                    {business.average_rating && (
                      <>
                        <span>•</span>
                        <div className="flex items-center gap-1">
                          <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                          <span>
                            {parseFloat(
                              business.average_rating.toString()
                            ).toFixed(1)}
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {business.description}
                  </p>

                  {business.address && (
                    <div className="flex items-center gap-2 text-sm">
                      <MapPin className="h-4 w-4 text-muted-foreground" />
                      <span className="text-muted-foreground">
                        {business.address}
                      </span>
                    </div>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
